#include "loginform.h"
#include <QVBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QLineEdit>

LoginForm::LoginForm(QWidget *parent) : QWidget(parent) {
    QVBoxLayout *layout = new QVBoxLayout(this);

    QLabel *titleLabel = new QLabel("Вход", this);
    titleLabel->setAlignment(Qt::AlignCenter);
    titleLabel->setStyleSheet("font-size: 24px; font-weight: bold;");
    layout->addWidget(titleLabel);

    QLabel *usernameLabel = new QLabel("Имя пользователя или e-mail", this);
    usernameLabel->setStyleSheet("font-size: 16px;");
    layout->addWidget(usernameLabel);

    usernameInput = new QLineEdit(this);
    usernameInput->setStyleSheet("border: 1px solid #ccc; border-radius: 5px; padding: 5px;");
    layout->addWidget(usernameInput);

    QLabel *passwordLabel = new QLabel("Пароль", this);
    passwordLabel->setStyleSheet("font-size: 16px;");
    layout->addWidget(passwordLabel);

    passwordInput = new QLineEdit(this);
    passwordInput->setEchoMode(QLineEdit::Password);
    passwordInput->setStyleSheet("border: 1px solid #ccc; border-radius: 5px; padding: 5px;");
    layout->addWidget(passwordInput);

    QPushButton *forgotPasswordButton = new QPushButton("Забыли пароль?", this);
    forgotPasswordButton->setStyleSheet("background-color: transparent; border: none; color: #007BFF;");
    layout->addWidget(forgotPasswordButton);

    loginButton = new QPushButton("Вход", this);
    loginButton->setStyleSheet("background-color: #007BFF; color: white; border: none; border-radius: 5px; padding: 10px;");
    layout->addWidget(loginButton);

    registerButton = new QPushButton("Регистрация", this);
    registerButton->setStyleSheet("background-color: #6C757D; color: white; border: none; border-radius: 5px; padding: 10px;");
    layout->addWidget(registerButton);

    connect(registerButton, &QPushButton::clicked, this, &LoginForm::registerClicked);
    connect(loginButton, &QPushButton::clicked, this, &LoginForm::loginSuccessful);
}
