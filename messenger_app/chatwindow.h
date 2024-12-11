#ifndef CHATWINDOW_H
#define CHATWINDOW_H

#include <QWidget>
#include <QLabel>
#include <QTextEdit>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>
#include "websocketclient.h"

class ChatWindow : public QWidget {
    Q_OBJECT

public:
    explicit ChatWindow(const QString &chatName, const QString &chatId, const QString &recipientId, QWidget *parent = nullptr);
    void setChatName(const QString &chatName);

signals:
    void backToChatList();

private slots:
    void sendMessage();
    void onMessageReceived(const QString &message);
    //void onBackToChatList();

private:
    QLabel *chatNameLabel;
    QTextEdit *messageDisplay;
    QLineEdit *messageInput;
    QPushButton *sendButton;
    QPushButton *backButton;
    WebSocketClient *webSocketClient;
    QUrl serverUrl;
    QString currentChatId;
    QString currentRecipientId;
};

#endif // CHATWINDOW_H
