#include "loginform.h"
#include <QVBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QLineEdit>
#include <QMessageBox>
#include <QNetworkAccessManager>
#include <QNetworkRequest>
#include <QNetworkReply>
#include <QJsonObject>
#include <QJsonDocument>
#include <QDebug>
#include <QSettings>
#include <QPalette>
#include <QColor>

LoginForm::LoginForm(QWidget *parent) : QWidget(parent) {
    QVBoxLayout *layout = new QVBoxLayout(this);

    //setFixedSize(300, 300);

    QPalette palette;
    palette.setColor(QPalette::Window, QColor("#E0F0F6"));
    setPalette(palette);
    setAutoFillBackground(true);

    QLabel *titleLabel = new QLabel("Вход", this);
    titleLabel->setAlignment(Qt::AlignCenter);
    titleLabel->setStyleSheet("font-size: 24px; font-weight: bold;");
    layout->addWidget(titleLabel);

    QLabel *usernameLabel = new QLabel("E-mail", this);
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

    loginButton = new QPushButton("Вход", this);
    loginButton->setStyleSheet("background-color: #007BFF; color: white; border: none; border-radius: 5px; padding: 10px;");
    layout->addWidget(loginButton);

    registerButton = new QPushButton("Регистрация", this);
    registerButton->setStyleSheet("background-color: #6C757D; color: white; border: none; border-radius: 5px; padding: 10px;");
    layout->addWidget(registerButton);

    connect(registerButton, &QPushButton::clicked, this, &LoginForm::onRegisterClicked);
    connect(loginButton, &QPushButton::clicked, this, &LoginForm::onLoginClicked);

    setLayout(layout);
}

void LoginForm::onRegisterClicked() {
    emit goToRegister();
}

void LoginForm::onLoginClicked() {
    QString email = usernameInput->text();
    QString password = passwordInput->text();

    /*дефолтные данные по которым можно войти в приложение
    const QString predefinedUsername = "admin";
    const QString predefinedPassword = "admin";

    if (email == predefinedUsername && password == predefinedPassword) {
        emit loginSuccessful();
    } else {
        QMessageBox::warning(this, "Ошибка входа", "Неверное имя пользователя или пароль.");
    }

    if (email.isEmpty() || password.isEmpty()) {
        QMessageBox::warning(this, "Ошибка входа", "Пожалуйста, заполните все поля.");
        return;
    }*/

    //QMessageBox::information(this, "Успешный вход", "Вы успешно вошли!");

    QNetworkAccessManager *manager = new QNetworkAccessManager(this);
    QUrl url(server_url);
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    QJsonObject jsonData;
    jsonData["email"] = email;
    jsonData["password"] = password;

    QJsonDocument doc(jsonData);
    QByteArray postData = doc.toJson();

    QNetworkReply *reply = manager->post(request, postData);
    connect(reply, &QNetworkReply::finished, [=]() {
        if (reply->error() == QNetworkReply::NoError) {
            QByteArray responseData = reply->readAll();
            QJsonDocument responseDoc = QJsonDocument::fromJson(responseData);
            QJsonObject responseObj = responseDoc.object();

            if (responseObj.contains("access_token") && responseObj.contains("refresh_token")) {
                QString accessToken = responseObj["access_token"].toString();
                QString refreshToken = responseObj["refresh_token"].toString();

                // Сохранение токенов
                QSettings settings;
                settings.setValue("access_token", accessToken);
                settings.setValue("refresh_token", refreshToken);

                // Переход в меню чатов
                QMessageBox::information(this, "Успешный вход", "Вы успешно вошли!");
                emit loginSuccessful();
            } else {
                QMessageBox::warning(this, "Ошибка входа", "Не удалось получить токены.");
            }
        } else {
            int statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            QByteArray responseData = reply->readAll();
            QJsonDocument responseDoc = QJsonDocument::fromJson(responseData);
            QJsonObject responseObj = responseDoc.object();

            if (statusCode == 400) {
                if (responseObj.contains("detail")) {
                    QString detail = responseObj["detail"].toString();
                    if (detail == "Email is already used") {
                        QMessageBox::warning(this, "Ошибка входа", "Неверная почта.");
                    } else if (detail == "Incorrect password") {
                        QMessageBox::warning(this, "Ошибка входа", "Неверный пароль.");
                    } else {
                        QMessageBox::warning(this, "Ошибка входа", "Неизвестная ошибка: " + detail);
                    }
                } else {
                    QMessageBox::warning(this, "Ошибка входа", "Неизвестная ошибка.");
                }
            } else {
                QMessageBox::warning(this, "Ошибка входа", "Ошибка при отправке данных на сервер: " + reply->errorString());
            }
        }
        reply->deleteLater();
    });
}
