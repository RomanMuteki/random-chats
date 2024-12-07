#include "chatwindow.h"

ChatWindow::ChatWindow(const QString &chatName, QWidget *parent) : QWidget(parent) {
    QVBoxLayout *layout = new QVBoxLayout(this);

    QPalette palette;
    palette.setColor(QPalette::Window, QColor("#E0F0F6"));
    setPalette(palette);
    setAutoFillBackground(true);

    backButton = new QPushButton("Назад", this);
    backButton->setStyleSheet("background-color: #6C757D; color: white; border: none; border-radius: 5px; padding: 10px;");
    layout->addWidget(backButton, 0, Qt::AlignLeft);
    connect(backButton, &QPushButton::clicked, this, &ChatWindow::backToChatList);

    chatNameLabel = new QLabel(chatName, this);
    chatNameLabel->setAlignment(Qt::AlignCenter);
    chatNameLabel->setStyleSheet("font-size: 24px; font-weight: bold;");
    layout->addWidget(chatNameLabel);

    messageDisplay = new QTextEdit(this);
    messageDisplay->setReadOnly(true);
    messageDisplay->setStyleSheet("border: 1px solid #ccc; border-radius: 5px; padding: 5px;");
    layout->addWidget(messageDisplay);

    messageInput = new QLineEdit(this);
    messageInput->setPlaceholderText("Введите сообщение...");
    messageInput->setStyleSheet("border: 1px solid #ccc; border-radius: 5px; padding: 5px;");
    layout->addWidget(messageInput);

    sendButton = new QPushButton("Отправить", this);
    sendButton->setStyleSheet("background-color: #007BFF; color: white; border: none; border-radius: 5px; padding: 10px;");
    layout->addWidget(sendButton);

    connect(sendButton, &QPushButton::clicked, this, &ChatWindow::sendMessage);
}

void ChatWindow::sendMessage() {
    QString message = messageInput->text();
    if (!message.isEmpty()) {
        messageDisplay->append(chatNameLabel->text() + ": " + message);
        messageInput->clear();
    }
}

void ChatWindow::setChatName(const QString &chatName) {
    chatNameLabel->setText(chatName);
}

