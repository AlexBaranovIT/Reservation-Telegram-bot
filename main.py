import telebot
from telebot import types
import datetime
import sqlite3
import threading
import os
from keepalive import keep_alive
import pytz 

# Replace 'YOUR_TELEGRAM_BOT_TOKEN' with the token you obtained from BotFather
bot = telebot.TeleBot(os.getenv('tg_key'))

# Set the timezone to any you want
tz = pytz.timezone('Asia/Nicosia')

keep_alive()
# Create thread-local storage for SQLite connection
local_storage = threading.local()

#Time slots for every user
available_time_slots = {}


#Gets database connection
def get_db_connection():
    # Check if a connection exists for the current thread, if not, create a new one
    if not hasattr(local_storage, 'db'):
        local_storage.db = sqlite3.connect('tennis_court_reservations.db')
        create_reservations_table()  # Ensure the table is created
    return local_storage.db


#Makes new reservation table
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
    # Set the timezone for Cyprus
    tz = pytz.timezone('Europe/Nicosia')

    # Convert the provided date to a timezone-aware datetime object at the start of the day
    aware_date_start = tz.localize(datetime.datetime.combine(date, datetime.time()))

    # Get the already reserved slots for the date
    reserved_slots = get_reserved_time_slots(date)

    # Generate list of available time slots for the selected date
    available_slots = [
        aware_date_start + datetime.timedelta(hours=h)
        for h in range(6, 22) # 6 AM to 10 PM
        if (aware_date_start + datetime.timedelta(hours=h)).strftime('%H:%M') not in reserved_slots
    ]

    return available_slots

def get_reserved_time_slots(date):
    cursor = get_db_connection().cursor()
    cursor.execute("SELECT reservation_time FROM reservations WHERE strftime('%Y-%m-%d', reservation_time) = ?", (date.strftime('%Y-%m-%d'),))
    reserved_times = cursor.fetchall()
    reserved_slots = [datetime.datetime.strptime(time[0], '%Y-%m-%d %H:%M').strftime('%H:%M') for time in reserved_times]
    return reserved_slots


def send_confirmation(chat_id, reservation_datetime, message):
    # Customize the message as required
    confirmation_message = "You have successfully reserved the tennis court on {}.".format(reservation_datetime.strftime('%Y-%m-%d %H:%M'))
    bot.send_message(chat_id, confirmation_message)
    save_reservations_to_file('reservations.txt')  # Save reservations to the file

    start_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    start_button = types.KeyboardButton('/start')
    reserve_button = types.KeyboardButton('/reserve')
    cancel_button = types.KeyboardButton('/cancel')
    support_button = types.KeyboardButton('/support')
    location_button = types.KeyboardButton('/location')

    start_markup.add(start_button, reserve_button, cancel_button, support_button, location_button)

    bot.send_message(message.chat.id, "Choose the function:", reply_markup=start_markup)


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
    start_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    start_button = types.KeyboardButton('/start')
    reserve_button = types.KeyboardButton('/reserve')
    cancel_button = types.KeyboardButton('/cancel')
    support_button = types.KeyboardButton('/support')
    location_button = types.KeyboardButton('/location')

    start_markup.add(start_button, reserve_button, cancel_button, support_button, location_button)
    bot.send_message(message.chat.id, "Welcome to the Tennis Court Reservation Bot!\n\nUse /start to start again.\n\nUse /reserve to book a court for 1 hour.\n\nUse /cancel to cancel your reservation.\n\nUse /support to text the support team.\n\nUse /location to get the court location.")
    bot.send_message(message.chat.id, "Choose the function:", reply_markup=start_markup)


@bot.message_handler(commands=['support'])
def on_start_command(message):
    # Send a message with the inline keyboard
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("Text support", url='https://t.me/ImAlex007')
    markup.add(btn)

    bot.send_message(message.chat.id, "Press the button to text the support team.", reply_markup=markup)
    start_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    start_button = types.KeyboardButton('/start')
    reserve_button = types.KeyboardButton('/reserve')
    cancel_button = types.KeyboardButton('/cancel')
    support_button = types.KeyboardButton('/support')
    location_button = types.KeyboardButton('/location')

    start_markup.add(start_button, reserve_button, cancel_button, support_button, location_button)
    bot.send_message(message.chat.id, "Choose the function:", reply_markup=start_markup)


@bot.message_handler(commands=['location'])
def send_location(message):
    # Replace these coordinates with the latitude and longitude of the location you want to send
    latitude = 34.70197266790477
    longitude = 33.07582804045963

    bot.send_location(message.chat.id, latitude, longitude)
    bot.send_message(message.chat.id, 'Court is near Sklavenitis Columbia Parking, behind Sklavenitis Columbia, Germasogeia Limassol')
    start_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    start_button = types.KeyboardButton('/start')
    reserve_button = types.KeyboardButton('/reserve')
    cancel_button = types.KeyboardButton('/cancel')
    support_button = types.KeyboardButton('/support')
    location_button = types.KeyboardButton('/location')

    start_markup.add(start_button, reserve_button, cancel_button, support_button, location_button)
    bot.send_message(message.chat.id, "Choose the function:", reply_markup=start_markup)


@bot.message_handler(commands=['reserve'])
def ask_for_date(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    cursor = get_db_connection().cursor()
    cursor.execute("SELECT reservation_time FROM reservations WHERE user_id=?", (user_id,))
    reservation_time = cursor.fetchone()

    if reservation_time:  # Check if reservation_time is not None
        reservation_time_naive = datetime.datetime.strptime(reservation_time[0], '%Y-%m-%d %H:%M')
        reservation_time_aware = tz.localize(reservation_time_naive)

        if reservation_time_aware > datetime.datetime.now(tz):
            bot.send_message(chat_id, "You already have a reservation on {}.".format(reservation_time[0]))
            return

    # Generate buttons for date selection
    markup = generate_date_selection_buttons()
    bot.send_message(chat_id, "Please select the date you want to play:", reply_markup=markup)


@bot.message_handler(commands=['cancel'])
def cancel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    cursor = get_db_connection().cursor()
    cursor.execute("SELECT reservation_time FROM reservations WHERE user_id=?", (user_id,))
    reservation_time = cursor.fetchone()

    if reservation_time:
        # Extract the reservation date
        reservation_date = datetime.datetime.strptime(reservation_time[0], '%Y-%m-%d %H:%M').date()

        # Delete the reservation
        delete_reservation_from_db(user_id)

        # Regenerate available time slots for the reservation date
        generate_available_time_slots(reservation_date)

        bot.send_message(chat_id, "Your reservation has been canceled.")
        save_reservations_to_file('reservations.txt')  # Save reservations to the file
    else:
        bot.send_message(chat_id, "You don't have any reservation to cancel.")
      

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
            # Save the available time slots to the dictionary for the user
            available_time_slots[user_id] = {'date': reservation_date, 'slots': available_slots}

            # Generate buttons for time selection
            markup = generate_time_selection_buttons(available_slots)
            bot.send_message(chat_id, "Available time slots for {}:".format(reservation_date.strftime('%Y-%m-%d')), reply_markup=markup)

    else:
        bot.send_message(chat_id, "Sorry, you can only reserve a time within the next 7 days.")


def generate_time_selection_buttons(available_slots):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    current_datetime = datetime.datetime.now(tz)

    # Generate buttons for each available time slot within the specified range (6 AM to 10 PM)
    for slot in available_slots:
        # Check if the slot is within the range and is not in the past or within the next 5 minutes (buffer time)
        if 6 <= slot.hour < 22 and slot >= current_datetime + datetime.timedelta(minutes=5):
            button = types.KeyboardButton(slot.strftime('%H:%M'))
            markup.add(button)

    return markup


@bot.message_handler(func=lambda message: message.text and message.text in [slot.strftime('%H:%M') for slot in available_time_slots.get(message.from_user.id, {}).get('slots', [])])
def process_time_selection(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    selected_time = message.text.strip()

    # Get the selected date
    selected_date = available_time_slots[user_id]['date']

    # Parse the selected time input
    selected_time_obj = datetime.datetime.strptime(selected_time, '%H:%M').time()

    # Combine the selected date and reservation time to create the reservation datetime
    reservation_datetime = datetime.datetime.combine(selected_date, selected_time_obj)

    # Add timezone information to the reservation datetime
    reservation_datetime = tz.localize(reservation_datetime)

    # Check if the reservation time is in the past
    if reservation_datetime < datetime.datetime.now(tz):
        bot.send_message(chat_id, "You cannot reserve a time in the past.")
    else:
        # Save the reservation to the database
        save_reservation_to_db(user_id, reservation_datetime.strftime('%Y-%m-%d %H:%M'))

        # Send confirmation message to the user
        send_confirmation(chat_id, reservation_datetime, message)  # You can use the existing function to send a confirmation message

    # Remove the selected time from available slots for the user
    available_time_slots[user_id]['slots'] = [slot for slot in available_time_slots[user_id]['slots'] if slot.strftime('%H:%M') != selected_time]
    available_time_slots[user_id]['slots'] = [slot for slot in available_time_slots[user_id]['slots'] if slot.astimezone(tz) > datetime.datetime.now(tz)]  # Remove past slots


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    selected_time = call.data  # Assuming that the callback data is the selected time
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    # Validate and process the selected time
    if selected_time in [slot.strftime('%H:%M') for slot in available_time_slots.get(user_id, {}).get('slots', [])]:
        # Process the reservation as above
        # ...
        bot.send_message(chat_id, f"Reservation successful for {selected_time}")
    else:
        bot.send_message(chat_id, "Invalid or unavailable reservation time. Please select a valid time from the available slots.")


# Polling loop to keep the bot running with none_stop=True
bot.polling(none_stop=True)
