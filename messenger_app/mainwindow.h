#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include "loginform.h"
#include "registerform.h"
#include "mainchatwindow.h"

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void showRegisterForm();
    void showLoginForm();
    void showMainChatWindow();

private:
    LoginForm *loginForm;
    RegisterForm *registerForm;
    MainChatWindow *mainChatWindow;
};

#endif // MAINWINDOW_H
