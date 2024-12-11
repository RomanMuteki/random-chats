import asyncio
import websockets
import tkinter as tk
from tkinter import scrolledtext, messagebox
import json
import threading
import time


username = ""
WS_URL = ""

async def listen_for_messages(ws, text_widget):
    global ws_connection
    ws_connection = ws
    while True:
        try:
            message = await ws.recv()
            if message == '{"type": "pong"}':
                print("pong")
            else:
                text_widget.insert(tk.END, f"Получено: {message}\n")
                text_widget.yview(tk.END)
        except websockets.ConnectionClosed:
            print("Connection closed.")
            break


async def send_message(ws, message, text_widget):
    if message:
        await ws.send(message)
        if message == '{"type": "ping"}':
            pass
        else:
            text_widget.insert(tk.END, f"Отправлено: {message}\n")
            text_widget.yview(tk.END)


async def websocket_client(text_widget, message_entry, send_button):
    global ws_connection
    async with websockets.connect(WS_URL) as ws:
        listen_task = asyncio.create_task(listen_for_messages(ws, text_widget))

        last_sent_time = time.time()

        while True:
            current_time = time.time()


            if current_time - last_sent_time > 30:
                ping_message = json.dumps({"type": "ping"})
                await send_message(ws, ping_message, text_widget)
                last_sent_time = current_time

            await asyncio.sleep(0.1)


def start_websocket_client(text_widget, message_entry, send_button):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_client(text_widget, message_entry, send_button))


def send_message_thread(message_entry, send_button, text_widget):
    message = message_entry.get("1.0", tk.END).strip()
    if message:
        try:
            json_message = json.loads(message)
            send_button.config(state=tk.DISABLED)
            threading.Thread(target=send_message_async, args=(json.dumps(json_message), text_widget, send_button), daemon=True).start()
            message_entry.delete("1.0", tk.END)
        except json.JSONDecodeError:
            if not hasattr(send_message_thread, 'error_shown') or not send_message_thread.error_shown:
                messagebox.showerror("Invalid JSON", "The message is not a valid JSON!")
                send_message_thread.error_shown = True


def send_message_async(message, text_widget, send_button):
    global ws_connection
    if ws_connection is not None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def send():
            await send_message(ws_connection, message, text_widget)
            send_button.config(state=tk.NORMAL)

        loop.run_until_complete(send())


def reset_error(send_button):
    send_button.config(state=tk.NORMAL)
    send_message_thread.error_shown = False

# Функция для ввода имени пользователя
def ask_for_username():
    def on_submit():
        global username, WS_URL
        username = entry.get()
        if username:
            WS_URL = f"ws://0.0.0.0:8001/ws/{username}"
            root.destroy()
        else:
            messagebox.showerror("Ошибка", "Имя пользователя не может быть пустым")

    root = tk.Tk()
    root.title("Введите имя пользователя")

    label = tk.Label(root, text="Пожалуйста, введите ваше имя:")
    label.pack(padx=10, pady=10)

    entry = tk.Entry(root, width=30)
    entry.pack(padx=10, pady=10)

    submit_button = tk.Button(root, text="Подтвердить", command=on_submit)
    submit_button.pack(pady=5)

    root.mainloop()


def create_gui():
    ask_for_username()

    window = tk.Tk()
    window.title("WebSocket Client")

    left_frame = tk.Frame(window)
    left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

    message_label = tk.Label(left_frame, text="Введите JSON сообщение:")
    message_label.pack()

    message_entry = scrolledtext.ScrolledText(left_frame, width=40, height=10)  # Многострочное поле для ввода
    message_entry.pack(padx=10)

    send_button = tk.Button(left_frame, text="Отправить", command=lambda: send_message_thread(message_entry, send_button, text_widget))
    send_button.pack(pady=5)

    right_frame = tk.Frame(window)
    right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

    messages_label = tk.Label(right_frame, text="Полученные и отправленные сообщения:")
    messages_label.pack()

    text_widget = scrolledtext.ScrolledText(right_frame, width=80, height=30, wrap=tk.WORD)  # Увеличили размер окна
    text_widget.pack()

    user_label = tk.Label(window, text=f"{username}", font=("Helvetica", 12))
    user_label.grid(row=1, column=0, columnspan=2, pady=10)

    window.grid_columnconfigure(0, weight=1)
    window.grid_columnconfigure(1, weight=2)

    threading.Thread(target=start_websocket_client, args=(text_widget, message_entry, send_button), daemon=True).start()

    # Закрытие окна
    def on_closing():
        print("Закрытие приложения...")
        window.quit()
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", on_closing)

    window.mainloop()


if __name__ == "__main__":
    create_gui()
