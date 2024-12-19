#include <QNetworkAccessManager>
#include <QNetworkRequest>
#include <QNetworkReply>
#include <QJsonObject>
#include <QJsonDocument>
#include <QMessageBox>
#include <QSettings>
#include <QDebug>
#include "mainwindow.h"
#include "loginform.h"
#include "registerform.h"
#include "mainchatwindow.h"
#include "chatwindow.h"

MainWindow::MainWindow(QWidget *parent) : QMainWindow(parent) {
    //chatWindow = new ChatWindow("", this);
    loginForm = new LoginForm(this);
    registerForm = new RegisterForm(this);
    mainChatWindow = new MainChatWindow(this);
    //chatWindow = nullptr;

    loginForm->setMinimumSize(300, 300);
    //loginForm->setMaximumSize(800, 600);

    registerForm->setMinimumSize(800, 600);
    //registerForm->setMaximumSize(1200, 800);

    mainChatWindow->setMinimumSize(600, 400);
    //mainChatWindow->setMaximumSize(1200, 800);

    setCentralWidget(loginForm);
    loginForm->show();
    registerForm->hide();
    mainChatWindow->hide();

    connect(loginForm, &LoginForm::goToRegister, this, &MainWindow::showRegisterForm);
    connect(registerForm, &RegisterForm::loginClicked, this, &MainWindow::showLoginForm);
    connect(loginForm, &LoginForm::loginSuccessful, this, &MainWindow::showMainChatWindow);
    connect(mainChatWindow, &MainChatWindow::chatSelected, this, &MainWindow::showChatWindow);
    connect(loginForm, &LoginForm::tokenValidationSuccessful, this, &MainWindow::showMainChatWindow);
}

MainWindow::~MainWindow() {}

void MainWindow::showRegisterForm() {
    qDebug() << "showRegisterForm";
    loginForm->hide();
    //delete registerForm;
    registerForm = new RegisterForm(this);
    registerForm->show();
    setCentralWidget(registerForm);

    connect(registerForm, &RegisterForm::loginClicked, this, &MainWindow::showLoginForm);
}

void MainWindow::showLoginForm() {
    qDebug() << "showLoginForm";
    registerForm->hide();
    qDebug() << "showLoginForm2";
    //delete loginForm;
    loginForm = new LoginForm(this);
    loginForm->show();
    qDebug() << "showLoginForm3";
    setCentralWidget(loginForm);

    connect(loginForm, &LoginForm::goToRegister, this, &MainWindow::showRegisterForm);
    connect(loginForm, &LoginForm::loginSuccessful, this, &MainWindow::showMainChatWindow);
}

void MainWindow::showMainChatWindow() {
    loginForm->hide();
    mainChatWindow = new MainChatWindow(this);
    mainChatWindow->show();
    qDebug() << "showMainChatWindow";
    setCentralWidget(mainChatWindow);

    connect(mainChatWindow, &MainChatWindow::chatSelected, this, &MainWindow::showChatWindow);
}

void MainWindow::showChatWindow(const QString &chatName, const QString &chatId, const QString &recipientId) {
    //if (chatWindow) {
    if (chatWindow != nullptr) {
        delete chatWindow;
        chatWindow = nullptr;
    }


    chatWindow = new ChatWindow(chatName, chatId, recipientId, this);
    connect(chatWindow, &ChatWindow::backToChatList, this, &MainWindow::showMainChatWindow);

    setCentralWidget(chatWindow);
}
  /*  QString handlerUrl = globalSettings->value("websocket_handler_url").toString();
    if (!handlerUrl.isEmpty()) {
        chatWindow->connectToWebSocket(handlerUrl);
    } else {
        qDebug() << "Ошибка: handler_url не найден.";
    }
}*/

