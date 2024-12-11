#ifndef MAINCHATWINDOW_H
#define MAINCHATWINDOW_H

#include <QWidget>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include "websocketclient.h"

class MainChatWindow : public QWidget {
    Q_OBJECT

public:
    explicit MainChatWindow(QWidget *parent = nullptr);
    QString matching_url = "http://192.168.0.141:8350/matching";

signals:
    void chatSelected(const QString &chatName, const QString &chatId, const QString &recipientId);

private slots:
    void onMessageReceived(const QString &message);
    void fetchChats();
    void updateChatList(const QJsonArray &chats);

private:
    QLineEdit *searchBar;
    QListWidget *chatList;
    QPushButton *addChatButton;
    WebSocketClient *webSocketClient;
};

#endif // MAINCHATWINDOW_H
