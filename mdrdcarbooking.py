from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, CallbackContext, filters
from datetime import datetime, timedelta
import os
import logging

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Fetch sensitive information from Secrets Manager
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # Admin Telegram chat ID
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")  # Car booking group chat ID

# Temporary storage for bookings and approval requests
bookings = []
pending_approvals = {}

# Start command
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Welcome to the Booking App! Choose an option:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Book Car", callback_data="book_car")],
            [InlineKeyboardButton("View Bookings", callback_data="view_bookings")],
            [InlineKeyboardButton("Cancel Booking", callback_data="cancel_booking")],
            [InlineKeyboardButton("Post All Bookings to Group", callback_data="post_bookings")]
        ])
    )

# Handle menu interactions
async def handle_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "book_car":
        today = datetime.now()
        buttons = [
            [InlineKeyboardButton(
                (today + timedelta(days=i)).strftime("%Y-%m-%d"),
                callback_data=f"select_date_{(today + timedelta(days=i)).strftime('%Y-%m-%d')}"
            )]
            for i in range(14)
        ]
        await query.edit_message_text(
            "Choose a date to book:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif query.data == "view_bookings":
        if bookings:
            booking_text = "\n".join([f"{b['date']} {b['time']} - {b['user']}" for b in bookings])
        else:
            booking_text = "No bookings yet!"
        await query.edit_message_text(
            f"Current Bookings:\n{booking_text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back to Menu", callback_data="menu")]
            ])
        )
    elif query.data == "cancel_booking":
        # List user's bookings for cancellation
        user = query.from_user.first_name
        user_bookings = [b for b in bookings if b['user'] == user]
        if user_bookings:
            buttons = [
                [InlineKeyboardButton(f"{b['date']} {b['time']}", callback_data=f"cancel_{i}")]
                for i, b in enumerate(bookings) if b['user'] == user
            ]
            buttons.append([InlineKeyboardButton("Back to Menu", callback_data="menu")])
            await query.edit_message_text(
                "Choose a booking to cancel:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await query.edit_message_text(
                "You have no bookings to cancel.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Back to Menu", callback_data="menu")]
                ])
            )
    elif query.data.startswith("cancel_"):
        # Cancel a specific booking
        booking_id = int(query.data.split("_")[1])
        booking = bookings.pop(booking_id)
        await query.edit_message_text("Booking cancelled successfully!")
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"🚫 *Booking Cancelled* 🚫\n\n"
                 f"🗓 Date: {booking['date']}\n"
                 f"⏰ Time: {booking['time']}\n"
                 f"👤 User: {booking['user']}",
            parse_mode="Markdown"
        )
    elif query.data == "post_bookings":
        if bookings:
            booking_text = "\n".join([f"{b['date']} {b['time']} - {b['user']}" for b in bookings])
        else:
            booking_text = "No bookings yet!"
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"📋 *All Bookings* 📋\n\n{booking_text}")
        await query.answer("Bookings have been posted to the group!")

    elif query.data == "menu":
        await query.edit_message_text(
            "Welcome to the Booking App! Choose an option:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Book Car", callback_data="book_car")],
                [InlineKeyboardButton("View Bookings", callback_data="view_bookings")],
                [InlineKeyboardButton("Cancel Booking", callback_data="cancel_booking")],
                [InlineKeyboardButton("Post All Bookings to Group", callback_data="post_bookings")]
            ])
        )

# Handle date selection
async def select_date(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    selected_date = query.data.split("_")[-1]
    context.user_data["selected_date"] = selected_date

    await query.edit_message_text(
        f"Selected date: {selected_date}\nPlease type the time range (e.g., 09:00-11:00)."
    )

# Handle time range input
async def handle_time_range(update: Update, context: CallbackContext):
    time_range = update.message.text.strip()
    selected_date = context.user_data.get("selected_date")

    if not selected_date:
        await update.message.reply_text("Error: No date selected. Please start the booking process again.")
        return

    user = update.message.from_user.first_name
    pending_id = len(pending_approvals)
    pending_approvals[pending_id] = {
        "date": selected_date,
        "time": time_range,
        "user": user
    }

    # Notify admin for approval
    buttons = [
        [InlineKeyboardButton("Approve", callback_data=f"approve_{pending_id}"),
         InlineKeyboardButton("Deny", callback_data=f"deny_{pending_id}")]
    ]
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"New Booking Request:\nDate: {selected_date}\nTime: {time_range}\nUser: {user}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await update.message.reply_text("Your booking request has been sent for approval.")

# Approve/Deny booking requests
async def approve_or_deny(update: Update, context: CallbackContext):
    query = update.callback_query
    action, pending_id = query.data.split("_")
    pending_id = int(pending_id)

    if pending_id not in pending_approvals:
        await query.answer("This request has already been processed or does not exist.")
        return

    approval = pending_approvals.pop(pending_id)

    if action == "approve":
        bookings.append(approval)
        await query.answer("Booking approved!")
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"🚗 *Booking Approved* 🚗\n\n"
                 f"🗓 Date: {approval['date']}\n"
                 f"⏰ Time: {approval['time']}\n"
                 f"👤 User: {approval['user']}",
            parse_mode="Markdown"
        )
    elif action == "deny":
        await query.answer("Booking denied!")
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"❌ *Booking Denied* ❌\n\n"
                 f"🗓 Date: {approval['date']}\n"
                 f"⏰ Time: {approval['time']}\n"
                 f"👤 User: {approval['user']}",
            parse_mode="Markdown"
        )

# Main function
def main():
    application = Application.builder().token(os.getenv("BOT_TOKEN")).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_menu, pattern="^book_car|view_bookings|menu|cancel_booking|post_bookings$"))
    application.add_handler(CallbackQueryHandler(select_date, pattern="^select_date_.*$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_range))
    application.add_handler(CallbackQueryHandler(approve_or_deny, pattern="^approve_.*|deny_.*$"))

    application.run_polling()

if __name__ == "__main__":
    main()
