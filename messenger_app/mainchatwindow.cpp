#include "mainchatwindow.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QLineEdit>
#include <QListWidget>

MainChatWindow::MainChatWindow(QWidget *parent) : QWidget(parent) {
    QVBoxLayout *mainLayout = new QVBoxLayout(this);

    searchBar = new QLineEdit(this);
    searchBar->setPlaceholderText("Поиск...");
    searchBar->setStyleSheet("border: 1px solid #ccc; border-radius: 5px; padding: 5px;");
    mainLayout->addWidget(searchBar);

    chatList = new QListWidget(this);
    chatList->setStyleSheet("border: 1px solid #ccc; border-radius: 5px; padding: 5px;");
    mainLayout->addWidget(chatList);

    chatList->addItem("Чат 1");
    chatList->addItem("Чат 2");
    chatList->addItem("Чат 3");

    addChatButton = new QPushButton("+", this);
    addChatButton->setStyleSheet("color: black; border: none; border-radius: 50%; font-size: 24px; padding: 10px;");
    addChatButton->setFixedSize(50, 50);

    QHBoxLayout *buttonLayout = new QHBoxLayout();
    buttonLayout->addStretch();
    buttonLayout->addWidget(addChatButton);
    mainLayout->addLayout(buttonLayout);

    setLayout(mainLayout);
}
