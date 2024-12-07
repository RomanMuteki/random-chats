#include "mainchatwindow.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QLineEdit>
#include <QListWidget>
#include <QPalette>
#include <QColor>
#include <QFont>
#include <QGraphicsDropShadowEffect>

MainChatWindow::MainChatWindow(QWidget *parent) : QWidget(parent) {
    QVBoxLayout *mainLayout = new QVBoxLayout(this);

    //setFixedSize(600,400);
    QPalette palette;
    palette.setColor(QPalette::Window, QColor("#E0F0F6"));
    setPalette(palette);
    setAutoFillBackground(true);

    searchBar = new QLineEdit(this);
    searchBar->setPlaceholderText("Поиск...");
    searchBar->setStyleSheet("QLineEdit { border: 1px solid #ccc; border-radius: 5px; padding: 5px; background: rgba(255, 255, 255, 0.8); }");
    mainLayout->addWidget(searchBar);

    chatList = new QListWidget(this);
    chatList->setStyleSheet("QListWidget { border: 1px solid #ccc; border-radius: 5px; padding: 5px; background: rgba(255, 255, 255, 0.8); }"
                            "QListWidget::item { padding: 10px; border: 1px solid #ddd; border-radius: 5px; margin: 5px; }"
                            "QListWidget::item:selected { background: #007BFF; color: white; border: 1px solid #0056b3; }");
    mainLayout->addWidget(chatList);

    QStringList chats = {"Чат 1", "Чат 2", "Чат 3"};
    for (const QString &chat : chats) {
        QListWidgetItem *item = new QListWidgetItem(chat, chatList);
        item->setBackground(QColor(255, 255, 255, 100)); // Полупрозрачный белый фон
        item->setForeground(Qt::black); // Черный текст
        item->setFont(QFont("Arial", 12, QFont::Bold)); // Жирный шрифт
        item->setSizeHint(QSize(0, 50)); // Увеличенный размер

        QGraphicsDropShadowEffect *shadowEffect = new QGraphicsDropShadowEffect;
        shadowEffect->setBlurRadius(10);
        shadowEffect->setColor(QColor(0, 0, 0, 50));
        shadowEffect->setOffset(2, 2);
        chatList->setItemWidget(item, new QWidget);
        chatList->itemWidget(item)->setGraphicsEffect(shadowEffect);
    }

    connect(chatList, &QListWidget::itemClicked, [this](QListWidgetItem *item) {
        emit chatSelected(item->text());
    });

    addChatButton = new QPushButton("+", this);
    QFont font = addChatButton->font();
    font.setBold(true);
    addChatButton->setFont(font);
    addChatButton->setStyleSheet("QPushButton {color: black; border: none; border-radius: 50%; font-size: 24px; padding: 10px; }"
                                 "QPushButton:hover { background: #0056b3; }"
                                 "QPushButton:pressed { background: #6C757D; }");
    addChatButton->setFixedSize(50, 50);

    QHBoxLayout *buttonLayout = new QHBoxLayout();
    buttonLayout->addStretch();
    buttonLayout->addWidget(addChatButton);
    mainLayout->addLayout(buttonLayout);

    setLayout(mainLayout);
}
