#ifndef REGISTERFORM_H
#define REGISTERFORM_H

#include <QWidget>
#include <QLineEdit>
#include <QPushButton>
#include <QRadioButton>
#include <QComboBox>

class RegisterForm : public QWidget {
    Q_OBJECT

public:
    explicit RegisterForm(QWidget *parent = nullptr);

signals:
    void loginClicked();

private slots:
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
};

#endif // REGISTERFORM_H
