import asyncio
import threading
import json
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext
import websockets

class MessengerClient:
    def __init__(self):
        self.username = None
        self.ws = None
        self.root = tk.Tk()
        self.root.title("WebSocket Messenger")
        self.root.geometry("600x500")
        self.create_login_window()

    def create_login_window(self):
        """Создает окно для ввода имени пользователя и подключения к серверу."""
        self.login_frame = tk.Frame(self.root)
        self.login_frame.pack(pady=20)

        tk.Label(self.login_frame, text="Введите ваше имя:", font=("Arial", 14)).pack(pady=5)
        self.username_entry = tk.Entry(self.login_frame, font=("Arial", 12))
        self.username_entry.pack(pady=5)
        tk.Button(self.login_frame, text="Подключиться", font=("Arial", 12), command=self.connect).pack(pady=10)

    def connect(self):
        """Подключается к WebSocket серверу с введенным именем пользователя."""
        self.username = self.username_entry.get()
        if not self.username:
            messagebox.showwarning("Ошибка", "Пожалуйста, введите ваше имя.")
            return
        self.login_frame.pack_forget()
        self.create_main_window()
        threading.Thread(target=self.start_event_loop).start()

    def create_main_window(self):
        """Создает основное окно приложения с интерфейсом для чатов."""
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(pady=10)

        button_frame = tk.Frame(self.main_frame)
        button_frame.pack()
        tk.Button(button_frame, text="Отключиться", font=("Arial", 12), command=self.disconnect).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Создать чат", font=("Arial", 12), command=self.create_chat).pack(side=tk.LEFT, padx=5)

        tk.Label(self.main_frame, text="Список чатов:", font=("Arial", 14)).pack(pady=5)

        self.chat_listbox = tk.Listbox(self.main_frame, width=50, height=15, font=("Arial", 12))
        self.chat_listbox.pack(pady=5)
        self.chat_listbox.bind('<<ListboxSelect>>', self.on_chat_select)

        self.chat_frame = tk.Frame(self.root)
        self.chat_frame.pack_forget()

        self.chats = {}  # Данные чатов
        self.current_chat_id = None
        self.current_recipient_id = None

    def create_chat(self):
        """Запрашивает имя пользователя для создания нового чата и отправляет запрос на сервер."""
        recipient_id = simpledialog.askstring("Создать чат", "Введите имя пользователя:")
        if not recipient_id or recipient_id == self.username:
            messagebox.showwarning("Ошибка", "Некорректное имя пользователя.")
            return
        asyncio.run_coroutine_threadsafe(self.send_create_chat(recipient_id), self.loop)

    async def send_create_chat(self, recipient_id):
        """Отправляет запрос на создание чата с указанным пользователем."""
        message = {
            "type": "create_chat",
            "recipient_id": recipient_id
        }
        await self.ws.send(json.dumps(message))

    def on_chat_select(self, event):
        """Обрабатывает выбор чата из списка и открывает окно чата."""
        if not self.chat_listbox.curselection():
            return
        index = self.chat_listbox.curselection()[0]
        chat_id = self.chat_listbox.get(index)
        chat = self.chats[chat_id]
        recipient_id = [p for p in chat['participants'] if p != self.username][0]
        self.open_chat(chat_id, recipient_id)

    def open_chat(self, chat_id, recipient_id):
        """Открывает окно чата с выбранным пользователем."""
        self.current_chat_id = chat_id
        self.current_recipient_id = recipient_id
        self.main_frame.pack_forget()
        self.create_chat_window()

    def create_chat_window(self):
        """Создает окно для обмена сообщениями в выбранном чате."""
        self.chat_frame.pack(pady=10)

        top_frame = tk.Frame(self.chat_frame)
        top_frame.pack()

        tk.Button(top_frame, text="Назад к чатам", font=("Arial", 12), command=self.back_to_chat_list).pack(side=tk.LEFT)
        tk.Label(top_frame, text=f"Чат с: {self.current_recipient_id}", font=("Arial", 14)).pack(side=tk.LEFT, padx=10)

        self.messages_text = scrolledtext.ScrolledText(self.chat_frame, width=60, height=20, font=("Arial", 12))
        self.messages_text.pack(pady=5)
        self.messages_text.config(state=tk.DISABLED)

        bottom_frame = tk.Frame(self.chat_frame)
        bottom_frame.pack(pady=5)

        self.message_entry = tk.Entry(bottom_frame, width=50, font=("Arial", 12))
        self.message_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="Отправить", font=("Arial", 12), command=self.send_message).pack(side=tk.LEFT)

        # Отображение сообщений
        self.display_messages(self.current_chat_id)

    def back_to_chat_list(self):
        """Возвращает пользователя к списку чатов."""
        self.chat_frame.pack_forget()
        self.current_chat_id = None
        self.current_recipient_id = None
        self.main_frame.pack()

    def display_chats(self):
        """Обновляет список чатов в интерфейсе."""
        self.chat_listbox.delete(0, tk.END)
        for chat_id, chat in self.chats.items():
            recipient_id = [p for p in chat['participants'] if p != self.username][0]
            self.chat_listbox.insert(tk.END, chat_id)

    def display_messages(self, chat_id):
        """Отображает сообщения в выбранном чате."""
        self.messages_text.config(state=tk.NORMAL)
        self.messages_text.delete(1.0, tk.END)
        chat = self.chats[chat_id]
        if chat and 'messages' in chat:
            for msg in chat['messages']:
                sender = msg['sender_id']
                content = msg['content']
                self.messages_text.insert(tk.END, f"{sender}: {content}\n")
        self.messages_text.config(state=tk.DISABLED)

    def send_message(self):
        """Отправляет сообщение в текущий чат."""
        content = self.message_entry.get()
        if not content:
            messagebox.showwarning("Ошибка", "Введите сообщение.")
            return
        message = {
            "type": "send_message",
            "recipient_id": self.current_recipient_id,
            "content": content,
            "chat_id": self.current_chat_id
        }
        asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(message)), self.loop)
        # Добавляем сообщение в чат
        chat = self.chats[self.current_chat_id]
        if 'messages' not in chat:
            chat['messages'] = []
        chat['messages'].append({
            "sender_id": self.username,
            "content": content
        })
        self.display_messages(self.current_chat_id)
        self.message_entry.delete(0, tk.END)

    def disconnect(self):
        """Отключается от WebSocket сервера и закрывает приложение."""
        if self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        self.root.destroy()

    def start_event_loop(self):
        """Запускает асинхронный цикл для обработки WebSocket соединения."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.websocket_handler())

    async def websocket_handler(self):
        """Управляет WebSocket соединением и обработкой сообщений."""
        async with websockets.connect(f"ws://localhost:8001/ws/{self.username}") as self.ws:
            await self.fetch_chats()
            await asyncio.gather(
                self.receive_messages(),
                self.send_pings()
            )

    async def receive_messages(self):
        """Получает и обрабатывает сообщения от WebSocket сервера."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                print("Received:", data)
                await self.handle_server_message(data)
        except websockets.ConnectionClosed:
            messagebox.showinfo("Соединение закрыто", "Соединение с сервером было закрыто.")
            self.root.quit()

    async def handle_server_message(self, data):
        """Обрабатывает сообщения, полученные от сервера."""
        if data['type'] == 'all_chats' or data['type'] == 'new_chats':
            for chat in data['data']:
                chat_id = chat['_id']
                self.chats[chat_id] = chat
                if 'messages' not in self.chats[chat_id]:
                    self.chats[chat_id]['messages'] = []
            self.display_chats()
        elif data['type'] == 'all_messages' or data['type'] == 'new_messages':
            chat_id = data['chat_id']
            if chat_id not in self.chats:
                self.chats[chat_id] = {'messages': []}
            if 'messages' not in self.chats[chat_id]:
                self.chats[chat_id]['messages'] = []
            self.chats[chat_id]['messages'].extend(data['data'])
            if self.current_chat_id == chat_id:
                self.display_messages(chat_id)
        elif data['type'] == 'message':
            chat_id = data['chat_id']
            if chat_id not in self.chats:
                await self.fetch_chats()
            if 'messages' not in self.chats[chat_id]:
                self.chats[chat_id]['messages'] = []
            self.chats[chat_id]['messages'].append({
                "sender_id": data['sender_id'],
                "content": data['content']
            })
            if self.current_chat_id == chat_id:
                self.display_messages(chat_id)
            else:
                messagebox.showinfo("Новое сообщение", "Новое сообщение в одном из чатов.")
        elif data['type'] == 'pong':
            print("Received pong from server.")

    async def fetch_chats(self):
        """Запрашивает все чаты пользователя у сервера."""
        message = {
            "type": "fetch_chats"
        }
        await self.ws.send(json.dumps(message))

    async def send_pings(self):
        """Периодически отправляет пинг-сообщения серверу для поддержания соединения."""
        while True:
            await asyncio.sleep(30)
            if self.ws.open:
                ping_message = {
                    "type": "ping"
                }
                await self.ws.send(json.dumps(ping_message))

    def run(self):
        """Запускает основной цикл Tkinter."""
        self.root.protocol("WM_DELETE_WINDOW", self.disconnect)
        self.root.mainloop()


if __name__ == "__main__":
    client = MessengerClient()
    client.run()
