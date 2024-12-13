#ifndef LOGINFORM_H
#define LOGINFORM_H

#include <QWidget>
#include <QLineEdit>
#include <QPushButton>
#include <QRadioButton>
#include <QComboBox>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>

class LoginForm : public QWidget {
    Q_OBJECT

public:
    explicit LoginForm(QWidget *parent = nullptr);
    QString server_url = "http://192.168.0.141:8300/login";

signals:
    void goToRegister();
    void loginSuccessful();

private slots:
    void onLoginClicked();
    void onRegisterClicked();

private:
    QLineEdit *usernameInput;
    QLineEdit *passwordInput;
    QPushButton *loginButton;
    QPushButton *registerButton;
};

#endif // LOGINFORM_H
