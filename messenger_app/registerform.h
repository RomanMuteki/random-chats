#ifndef REGISTERFORM_H
#define REGISTERFORM_H

#include <QWidget>
#include <QLineEdit>
#include <QPushButton>
#include <QRadioButton>
#include <QComboBox>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>

class RegisterForm : public QWidget {
    Q_OBJECT

public:
    explicit RegisterForm(QWidget *parent = nullptr);
    QString server_url = "http://192.168.0.141:8300/register";

signals:
    void loginClicked();

private slots:
    void onLoginClicked();
    void onRegisterClicked();

private:
    QLineEdit *emailInput;
    QLineEdit *usernameInput;
    QLineEdit *passwordInput;
    QLineEdit *confirmPasswordInput;
    QLineEdit *ageInput;
    QRadioButton *maleRadio;
    QRadioButton *femaleRadio;
    QPushButton *registerButton;
    QPushButton *loginButton;
    QComboBox *genderPrefCombo;
    QComboBox *agePrefCombo;
    QNetworkAccessManager *networkManager;
};

#endif // REGISTERFORM_H
