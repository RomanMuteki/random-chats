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
#include <QSettings>
extern QSettings* globalSettings;
void initGlobalSettings();

class LoginForm : public QWidget {
    Q_OBJECT

public:
    explicit LoginForm(QWidget *parent = nullptr);
    QString server_url = "http://212.34.139.173:8500/login";
    QString url = "http://212.34.139.173:8500/token_login";

signals:
    void goToRegister();
    void loginSuccessful();
    void tokenValidationSuccessful();

private slots:
    void onLoginClicked();
    void onRegisterClicked();
    void checkAndValidateTokens();

private:
    bool checkTokens();
    void validateTokens();
    QLineEdit *usernameInput;
    QLineEdit *passwordInput;
    QPushButton *loginButton;
    QPushButton *registerButton;
};

#endif // LOGINFORM_H
