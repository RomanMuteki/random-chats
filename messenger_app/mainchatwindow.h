#ifndef MAINCHATWINDOW_H
#define MAINCHATWINDOW_H

#include <QWidget>
#include <QLabel>
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
    QString matching_url = "http://212.34.139.173:8500/matching";

signals:
    void chatSelected(const QString &chatName, const QString &chatId, const QString &recipientId);

private slots:
    void onMessageReceived(const QString &message);
    void fetchChats();
    //void updateChatList(const QJsonArray &chats);
    void allChatsHendler(const QJsonArray &chats);
    void allMessagesHendller(const QJsonArray &messages);
    void newChatsHendler(const QJsonArray &newChats);
    void createNewChat();
    void filterChats();
    void getWebSocketHandler();
    void updateMessagesForChat(const QString &chatId, const QJsonArray &messages);

private:
    QLabel *searchBar;
    QListWidget *chatList;
    QPushButton *addChatButton;
    WebSocketClient *webSocketClient;
};

#endif // MAINCHATWINDOW_H
