#include "mainwindow.h"
#include "loginform.h"
#include "registerform.h"
#include "mainchatwindow.h"

MainWindow::MainWindow(QWidget *parent) : QMainWindow(parent) {
    loginForm = new LoginForm(this);
    registerForm = new RegisterForm(this);
    mainChatWindow = new MainChatWindow(this);

    setCentralWidget(loginForm);

    connect(loginForm, &LoginForm::registerClicked, this, &MainWindow::showRegisterForm);
    connect(registerForm, &RegisterForm::loginClicked, this, &MainWindow::showLoginForm);
    connect(loginForm, &LoginForm::loginSuccessful, this, &MainWindow::showMainChatWindow);
}

MainWindow::~MainWindow() {}

void MainWindow::showRegisterForm() {
    setCentralWidget(registerForm);
}

void MainWindow::showLoginForm() {
    setCentralWidget(loginForm);
}

void MainWindow::showMainChatWindow() {
    setCentralWidget(mainChatWindow);
}
