from telebot import TeleBot, types
from datetime import datetime as dt
import sqlite3
from datetime import time
import threading
import os
from keepalive import keep_alive
import pytz
import datetime
from PIL import Image, ImageDraw, ImageFont
   
# Replace 'YOUR_TELEGRAM_BOT_TOKEN' with the token you obtained from BotFather
bot = TeleBot(os.getenv('tg_key'))

# Set the timezone to Nicosia, Cyprus (GMT+3)
tz = pytz.timezone('Asia/Nicosia') 
 
#Call keep_alive function to connect to the flask server
keep_alive()

# Create thread-local storage for SQLite connection
local_storage = threading.local()

#Stores all user's reservations
available_time_slots = {}


def get_db_connection():
    # Check if a connection exists for the current thread, if not, create a new one
    if not hasattr(local_storage, 'db'):
        local_storage.db = sqlite3.connect('tennis_court_reservation.db')
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


def generate_reservation_image(first_name, last_name, date, time):
    # Create a blank white image
    image = Image.new('RGB', (800, 400), color='white')

    # Create an ImageDraw object to draw on the image
    draw = ImageDraw.Draw(image)

    # Load the Arial font with size 20
    font = ImageFont.truetype("arial", size=20)

    # Define the texts
    texts = [f"Name: {first_name} {last_name}", f"Date: {date}", f"Time: {time}"]

    # Calculate total text height
    total_text_height = sum(draw.textsize(text, font=font)[1] for text in texts)

    # Start the y_offset in the middle of the image minus half of the total text height
    y_offset = (image.height - total_text_height) // 2

    # Draw each line of text
    for text in texts:
        text_width, text_height = draw.textsize(text, font=font)
        x_position = (image.width - text_width) // 2
        draw.text((x_position, y_offset), text, font=font, fill='black')
        y_offset += text_height + 10  # add some space between lines

    # Save the image to a file (optional)
    image_path = f"{first_name}_{last_name}_{date}_{time}.png"
    image.save(image_path)

    return image, image_path


def generate_date_selection_buttons():
    # Get the current date and time
    current_time = dt.now()

    # Create an InlineKeyboardMarkup to hold the buttons
    markup = telebot.types.InlineKeyboardMarkup()

    # Generate buttons for the next 7 days
    for i in range(7):
        date = current_time + timedelta(days=i)
        # Create an InlineKeyboardButton with the date as the callback_data
        button = telebot.types.InlineKeyboardButton(text=date.strftime('%b %d'), callback_data=date.strftime('%Y-%m-%d'))
        markup.add(button)

    return markup


def generate_available_time_slots(date):
    # Set the timezone for Cyprus
    tz = pytz.timezone('Europe/Nicosia')

    # Create a time object for the start of the day
    start_of_day = time(0, 0)

    # Convert the provided date to a timezone-aware datetime object at the start of the day
    aware_date_start = tz.localize(dt.combine(date, start_of_day))

    # Get the already reserved slots for the date
    reserved_slots = get_reserved_time_slots(date)

    # Generate list of available time slots for the selected date
    available_slots = [
        aware_date_start + timedelta(hours=h)
        for h in range(6, 22) # 6 AM to 10 PM
        if (aware_date_start + timedelta(hours=h)).strftime('%H:%M') not in reserved_slots
    ]

    return available_slots


def get_reserved_time_slots(date):
    cursor = get_db_connection().cursor()
    cursor.execute("SELECT reservation_time FROM reservations WHERE strftime('%Y-%m-%d', reservation_time) = ?", (date.strftime('%Y-%m-%d'),))
    reserved_times = cursor.fetchall()
    reserved_slots = [datetime.strptime(time[0], '%Y-%m-%d %H:%M').strftime('%H:%M') for time in reserved_times]
    return reserved_slots


def send_confirmation(chat_id, reservation_datetime, message, user_info):
    # Get the user information
    user_info = get_user_info(chat_id)
    user_id = message.from_user.id
    first_name = user_info['first_name']
    last_name = user_info.get('last_name', '')

    # Generate the reservation details text
    reservation_details = (
        f"Name: {first_name} {last_name}\n"
        f"Date: {reservation_datetime.strftime('%Y-%m-%d')}\n"
        f"Time: {reservation_datetime.strftime('%H:%M')}"
    )
    # Create an image to hold the text
    image = Image.new('RGB', (300, 150), color='white')
    draw = ImageDraw.Draw(image)

    # Select font and size (you might need to specify the path to a font file) 
    font_path = "arial.ttf"  # Path to your font file
    font = ImageFont.truetype(font_path, size=20)

    # Draw the text onto the image 
    draw.text((10, 10), reservation_details, fill="black", font=font)

    # Save the image to a temporary file
    image_path = 'reservation.png'
    image.save(image_path)

    # Send the image to the user
    with open(image_path, 'rb') as photo:
        bot.send_photo(chat_id, photo, caption="Congratulations! You have successfully reserved the tennis court!")

    # Remove the temporary image file
    os.remove(image_path)
    new_reservation = (user_id, reservation_datetime)
    # Get all the user's reservations and save them to the file
    save_reservation_to_file(new_reservation, 'reservations.txt') 

    start_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    start_button = types.KeyboardButton('/start')
    reserve_button = types.KeyboardButton('/reserve')
    cancel_button = types.KeyboardButton('/cancel')
    support_button = types.KeyboardButton('/support')
    location_button = types.KeyboardButton('/location')

    start_markup.add(start_button, reserve_button, cancel_button, support_button, location_button)
    bot.send_message(message.chat.id, "Choose the function:", reply_markup=start_markup)


def save_reservation_to_file(reservation, file_path):
    user_id, reservation_time = reservation
    
    # Check if the reservation_time is a datetime object
    if isinstance(reservation_time, datetime):
        reservation_time_formatted = reservation_time.strftime("%Y-%m-%d %H:%M")
    else:
        reservation_time_formatted = reservation_time # You may need to adapt this line to fit your specific case

    user_info = get_user_info(user_id)
    first_name = user_info['first_name']
    last_name = user_info.get('last_name', '')
    reservation_info = f"User ID: {user_id}, Name: {first_name} {last_name}, Reservation Date and Time: {reservation_time_formatted}\n"

    with open(file_path, 'a') as file:
        file.write(reservation_info)



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
    btn = types.InlineKeyboardButton("Text support", url='https://t.me/ImMrAlex')
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
        reservation_time_naive = dt.strptime(reservation_time[0], '%Y-%m-%d %H:%M')
        reservation_time_aware = tz.localize(reservation_time_naive)

        if reservation_time_aware > dt.now(tz):
            bot.send_message(chat_id, "You already have a reservation on {}. You can't make a new reservation until this one is past.".format(reservation_time[0]))
            return
        else:
            # Delete previous reservation if it already happened
            delete_reservation_from_db(user_id)

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
        reservation_date = dt.strptime(reservation_time[0], '%Y-%m-%d %H:%M').date()

        # Delete the reservation
        delete_reservation_from_db(user_id)

        # Regenerate available time slots for the reservation date
        generate_available_time_slots(reservation_date)

        bot.send_message(chat_id, "Your reservation has been canceled.")
        new_reservation = (user_id, reservation_time[0] + ", canceled")
        save_reservation_to_file(new_reservation, 'reservations.txt')
    else:
        bot.send_message(chat_id, "You don't have any reservation to cancel.")

      
@bot.callback_query_handler(func=lambda call: True)
def process_date_selection(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    selected_date = call.data

    # Get the selected date as a datetime object
    reservation_date = dt.strptime(selected_date, '%Y-%m-%d').date()

    # Check if the selected date is within the next 7 days
    current_time = dt.now().date()
    next_7_days = current_time + timedelta(days=7)

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
    current_datetime = dt.now(tz)  # Replace datetime.datetime with dt

    # Generate buttons for each available time slot within the specified range (6 AM to 10 PM)
    for slot in available_slots:
        # Check if the slot is within the range and is not in the past or within the next 5 minutes (buffer time)
        if 6 <= slot.hour < 22 and slot >= current_datetime + timedelta(minutes=5):  # Replace datetime.timedelta with timedelta
            button = types.KeyboardButton(slot.strftime('%H:%M'))
            markup.add(button)

    return markup


@bot.message_handler(func=lambda message: message.text and message.text in [slot.strftime('%H:%M') for slot in available_time_slots.get(message.from_user.id, {}).get('slots', [])])
def process_time_selection(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    selected_time = message.text.strip()

    # Get the selected date from the available_time_slots dictionary
    selected_date = available_time_slots[user_id]['date']

    # Parse the selected time input
    selected_time_obj = dt.strptime(selected_time, '%H:%M').time()

    # Combine the selected date and reservation time to create the reservation datetime
    reservation_datetime = dt.combine(selected_date, selected_time_obj)

    # Add timezone information to the reservation datetime
    reservation_datetime = tz.localize(reservation_datetime)

    # Check if the reservation time is in the past
    if reservation_datetime < dt.now(tz):
        bot.send_message(chat_id, "You cannot reserve a time in the past.")
    else:
        # Save the reservation to the database
        save_reservation_to_db(user_id, reservation_datetime.strftime('%Y-%m-%d %H:%M'))

        # Send confirmation message to the user
        user_info = get_user_info(user_id)
        send_confirmation(chat_id, reservation_datetime, message, user_info)

        # Remove the selected time from available slots for the user
        available_time_slots[user_id]['slots'] = [slot for slot in available_time_slots[user_id]['slots'] if slot.strftime('%H:%M') != selected_time]
        available_time_slots[user_id]['slots'] = [slot for slot in available_time_slots[user_id]['slots'] if slot.astimezone(tz) > dt.now(tz)]  # Remove past slots


@bot.message_handler(content_types=['text'])
def handle_text(message):
    start_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    start_button = types.KeyboardButton('/start')
    reserve_button = types.KeyboardButton('/reserve')
    cancel_button = types.KeyboardButton('/cancel')
    support_button = types.KeyboardButton('/support')
    location_button = types.KeyboardButton('/location')

    start_markup.add(start_button, reserve_button, cancel_button, support_button, location_button)
    text_answer_message = "Choose command to continue: "
    bot.send_message(message.chat.id, text_answer_message, reply_markup=start_markup)
 

# Polling loop to keep the bot running with none_stop=True
bot.polling(none_stop=True)
