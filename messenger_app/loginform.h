#ifndef LOGINFORM_H
#define LOGINFORM_H

#include <QWidget>
#include <QLineEdit>
#include <QPushButton>

class LoginForm : public QWidget {
    Q_OBJECT

public:
    explicit LoginForm(QWidget *parent = nullptr);

signals:
    void registerClicked();
    void loginSuccessful();

private:
    QLineEdit *usernameInput;
    QLineEdit *passwordInput;
    QPushButton *loginButton;
    QPushButton *registerButton;
};

#endif // LOGINFORM_H
