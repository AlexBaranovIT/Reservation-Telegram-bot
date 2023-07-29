import telebot
from telebot import types
import datetime
import sqlite3
import threading
import os
from keepalive import keep_alive

# Replace 'tg_key' with the token you obtained from BotFather
bot = telebot.TeleBot(os.getenv('tg_key'))

keep_alive()

# Create thread-local storage for SQLite connection
local_storage = threading.local()


def get_db_connection():
    # Check if a connection exists for the current thread, if not, create a new one
    if not hasattr(local_storage, 'db'):
        local_storage.db = sqlite3.connect('tennis_court_reservations.db')
        create_reservations_table()  # Ensure the table is created
    return local_storage.db


def create_reservations_table():
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            user_id INTEGER PRIMARY KEY,
            reservation_time TEXT
        );
    ''')
    db_connection.commit()


def save_reservation_to_db(user_id, reservation_time):
    cursor = get_db_connection().cursor()
    cursor.execute("INSERT INTO reservations (user_id, reservation_time) VALUES (?, ?)", (user_id, reservation_time))
    get_db_connection().commit()


def delete_reservation_from_db(user_id):
    cursor = get_db_connection().cursor()
    cursor.execute("DELETE FROM reservations WHERE user_id=?", (user_id,))
    get_db_connection().commit()


def generate_date_selection_buttons():
    # Get the current date and time
    current_time = datetime.datetime.now()

    # Create an InlineKeyboardMarkup to hold the buttons
    markup = telebot.types.InlineKeyboardMarkup()

    # Generate buttons for the next 7 days
    for i in range(7):
        date = current_time + datetime.timedelta(days=i)
        # Create an InlineKeyboardButton with the date as the callback_data
        button = telebot.types.InlineKeyboardButton(text=date.strftime('%b %d'), callback_data=date.strftime('%Y-%m-%d'))
        markup.add(button)

    return markup


def generate_available_time_slots(date):
    # Generate list of available time slots for the selected date
    available_slots = [
        datetime.datetime.combine(date, datetime.time(hour=h))
        for h in range(8, 22)
    ]

    cursor = get_db_connection().cursor()
    cursor.execute("SELECT reservation_time FROM reservations WHERE reservation_time LIKE ?", ("%{}%".format(date),))
    reserved_times = [datetime.datetime.strptime(res[0], '%Y-%m-%d %H:%M') for res in cursor.fetchall()]

    # Filter out already reserved slots
    available_slots = [slot for slot in available_slots if slot not in reserved_times]

    return available_slots


def send_confirmation(chat_id, reservation_datetime):
    # Send confirmation message to the user
    bot.send_message(chat_id, "You have successfully reserved the tennis court on {}.".format(reservation_datetime.strftime('%Y-%m-%d %H:%M')))
    save_reservations_to_file('reservations.txt')  # Save reservations to the file


def save_reservations_to_file(file_path):
    reservations = get_all_reservations()

    with open(file_path, 'w') as file:
        for res in reservations:
            user_id = res[0]
            reservation_time = res[1]

            # Get the user's first name and last name using the Telegram API
            user_info = get_user_info(user_id)
            first_name = user_info['first_name']
            last_name = user_info.get('last_name', '')

            file.write(f"User ID: {user_id}, Name: {first_name} {last_name}, Reservation Time: {reservation_time}\n")


def get_all_reservations():
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute("SELECT user_id, reservation_time FROM reservations")
    return cursor.fetchall()


def get_user_info(user_id):
    try:
        user = bot.get_chat(user_id)
        return {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
    except Exception as e:
        print(f"Failed to get user information for user_id {user_id}: {e}")
        return {}


@bot.message_handler(commands=['start'])
def send_welcome(message):
    start_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    start_button = types.KeyboardButton('/start')
    reserve_button = types.KeyboardButton('/reserve')
    cancel_button = types.KeyboardButton('/cancel')

    start_markup.add(start_button, reserve_button, cancel_button)
    bot.send_message(message.chat.id, "Welcome to the Tennis Court Reservation Bot!\nUse /start to start again.\nUse /reserve to book a court for 1 hour.\nUse /cancel to cancel your reservation.")
    bot.send_message(message.chat.id, "Choose the function:", reply_markup=start_markup)


@bot.message_handler(commands=['reserve'])
def ask_for_date(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    cursor = get_db_connection().cursor()
    cursor.execute("SELECT reservation_time FROM reservations WHERE user_id=?", (user_id,))
    reservation_time = cursor.fetchone()

    if reservation_time:
        bot.send_message(chat_id, "You already have a reservation on {}.".format(reservation_time[0]))
    else:
        # Generate inline buttons for date selection
        markup = generate_date_selection_buttons()
        bot.send_message(chat_id, "Please select the date you want to play:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def process_date_selection(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    selected_date = call.data

    # Get the selected date as a datetime object
    reservation_date = datetime.datetime.strptime(selected_date, '%Y-%m-%d').date()

    # Check if the selected date is within the next 7 days
    current_time = datetime.datetime.now().date()
    next_7_days = current_time + datetime.timedelta(days=7)

    if current_time <= reservation_date <= next_7_days:
        # Generate list of available time slots for the selected date
        available_slots = generate_available_time_slots(reservation_date)

        if not available_slots:
            bot.send_message(chat_id, "Sorry, no available time slots for {}.".format(reservation_date.strftime('%Y-%m-%d')))
        else:
            available_time_slots = "\n".join(slot.strftime('%H:%M') for slot in available_slots)
            bot.send_message(chat_id, "Available time slots for {}:\n{}".format(reservation_date.strftime('%Y-%m-%d'), available_time_slots))
            bot.send_message(chat_id, "Type the time you want to play. For example: 09:00")
    else:
        bot.send_message(chat_id, "Sorry, you can only reserve a time within the next 7 days.")


@bot.message_handler(commands=['cancel'])
def cancel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    cursor = get_db_connection().cursor()
    cursor.execute("SELECT reservation_time FROM reservations WHERE user_id=?", (user_id,))
    reservation_time = cursor.fetchone()

    if reservation_time:
        delete_reservation_from_db(user_id)
        bot.send_message(chat_id, "Your reservation has been canceled.")
        save_reservations_to_file('reservations.txt')  # Save reservations to the file
    else:
        bot.send_message(chat_id, "You don't have any reservation to cancel.")


@bot.message_handler(func=lambda message: message.text and ':' in message.text and '/reserve' not in message.text and '/cancel' not in message.text)
def process_time_input(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    time_input = message.text.strip()

    try:
        reservation_time = datetime.datetime.strptime(time_input, '%H:%M').time()

        # Check if the reservation time is within the valid range (8 AM to 9 PM)
        if datetime.time(8, 0) <= reservation_time <= datetime.time(21, 0):
            # Get the current date
            current_date = datetime.datetime.now().date()

            # Combine the current date and reservation time to create the reservation datetime
            reservation_datetime = datetime.datetime.combine(current_date, reservation_time)

            # Save the reservation to the database
            save_reservation_to_db(user_id, reservation_datetime.strftime('%Y-%m-%d %H:%M'))

            # Send confirmation message to the user
            bot.send_message(chat_id, "You have successfully reserved the tennis court on {}.".format(reservation_datetime.strftime('%Y-%m-%d %H:%M')))
            save_reservations_to_file('reservations.txt')  # Save reservations to the file
        else:
            bot.send_message(chat_id, "Invalid reservation time. Please enter a time between 8 AM and 9 PM (e.g., 09:00).")

    except ValueError:
        bot.send_message(chat_id, "Invalid time format. Please enter the time in HH:MM format (e.g., 09:00).")


# Polling loop to keep the bot running with none_stop=True
bot.polling(none_stop=True)
