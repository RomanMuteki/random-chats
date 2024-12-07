#ifndef CHATWINDOW_H
#define CHATWINDOW_H

#include <QWidget>
#include <QLabel>
#include <QTextEdit>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>

class ChatWindow : public QWidget {
    Q_OBJECT

public:
    explicit ChatWindow(const QString &chatName, QWidget *parent = nullptr);
    void setChatName(const QString &chatName);

signals:
    void backToChatList();

private slots:
    void sendMessage();

private:
    QLabel *chatNameLabel;
    QTextEdit *messageDisplay;
    QLineEdit *messageInput;
    QPushButton *sendButton;
    QPushButton *backButton;
};

#endif // CHATWINDOW_H
