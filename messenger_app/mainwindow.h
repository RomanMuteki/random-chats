#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include "loginform.h"
#include "registerform.h"
#include "mainchatwindow.h"
#include "chatwindow.h"

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void showRegisterForm();
    void showLoginForm();
    void showMainChatWindow();
    void showChatWindow(const QString &chatName, const QString &chatId, const QString &recipientId);

private:
    LoginForm *loginForm;
    RegisterForm *registerForm;
    MainChatWindow *mainChatWindow;
    ChatWindow *chatWindow;
};

#endif // MAINWINDOW_H
