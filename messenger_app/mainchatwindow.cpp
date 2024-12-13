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
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonDocument>
#include <QMessageBox>
#include <QNetworkAccessManager>
#include <QNetworkRequest>
#include <QNetworkReply>
#include <QSettings>
#include "websocketclient.h"
#include "loginform.h"

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
    connect(searchBar, &QLineEdit::textChanged, this, &MainChatWindow::filterChats);

    chatList = new QListWidget(this);
    chatList->setStyleSheet("QListWidget { border: 1px solid #ccc; border-radius: 5px; padding: 5px; background: rgba(255, 255, 255, 0.8); }"
                            "QListWidget::item { padding: 10px; border: 1px solid #ddd; border-radius: 5px; margin: 5px; }"
                            "QListWidget::item:selected { background: #007BFF; color: white; border: 1px solid #0056b3; }");
    mainLayout->addWidget(chatList);


    addChatButton = new QPushButton("+", this);
    QFont font = addChatButton->font();
    font.setBold(true);
    addChatButton->setFont(font);
    addChatButton->setStyleSheet("QPushButton {color: black; border: none; border-radius: 50%; font-size: 24px; padding: 10px; }"
                                 "QPushButton:hover { background: #0056b3; }"
                                 "QPushButton:pressed { background: #6C757D; }");
    addChatButton->setFixedSize(50, 50);
    connect(addChatButton, &QPushButton::clicked, this, &MainChatWindow::createNewChat);

    QHBoxLayout *buttonLayout = new QHBoxLayout();
    buttonLayout->addStretch();
    buttonLayout->addWidget(addChatButton);
    mainLayout->addLayout(buttonLayout);

    setLayout(mainLayout);

    webSocketClient = new WebSocketClient(this);
    connect(webSocketClient, &WebSocketClient::messageReceived, this, &MainChatWindow::onMessageReceived);

    webSocketClient->connectToServer(QUrl("ws://192.168.243.187:8001/ws/user1"));

    //Запрашиваем список чатов
    fetchChats();

    connect(chatList, &QListWidget::itemClicked, [this](QListWidgetItem *item) {
        QString chatName = item->text();
        QString chatId = item->data(Qt::UserRole).toString();
        QString recipientId = item->data(Qt::UserRole + 1).toString();
        emit chatSelected(chatName, chatId, recipientId);
    });
}

void MainChatWindow::fetchChats() {
    // Отправляем запрос на получение списка чатов
    QJsonObject request;
    request["type"] = "fetch_chats";
    QJsonDocument doc(request);
    QString jsonString = QString::fromUtf8(doc.toJson(QJsonDocument::Compact));
    webSocketClient->sendMessage(jsonString);
}


void MainChatWindow::updateChatList (const QJsonArray &chats) {
    chatList->clear();
    for (const QJsonValue &chat : chats) {
        QJsonObject chatObj = chat.toObject();
        QString chatName = chatObj["name"].toString();
        QString chatId = chatObj["_id"].toString();
        QString recipientId = chatObj["participants"].toArray().first().toString();

        QListWidgetItem *item = new QListWidgetItem(chatName, chatList);
        item->setData(Qt::UserRole, chatId);
        item->setData(Qt::UserRole + 1, recipientId);
        item->setBackground(QColor(255, 255, 255, 100));
        item->setForeground(Qt::black);
        item->setFont(QFont("Arial", 12, QFont::Bold));
        item->setSizeHint(QSize(0, 50));

        QGraphicsDropShadowEffect *shadowEffect = new QGraphicsDropShadowEffect;
        shadowEffect->setBlurRadius(10);
        shadowEffect->setColor(QColor(0, 0, 0, 50));
        shadowEffect->setOffset(2, 2);
        chatList->setItemWidget(item, new QWidget);
        chatList->itemWidget(item)->setGraphicsEffect(shadowEffect);
    }
}

void MainChatWindow::onMessageReceived(const QString &message) {
    QJsonDocument doc = QJsonDocument::fromJson(message.toUtf8());
    QJsonObject obj = doc.object();

    if (obj["type"] == "all_chats" || obj["type"] == "new_chats") {
        QJsonArray chats = obj["data"].toArray();
        updateChatList(chats);
    } else if (obj["type"] == "all_messages" || obj["type"] == "new_messages") {
        QString chatId = obj["chat_id"].toString();
        QJsonArray messages = obj["data"].toArray();
        // Обработка сообщений для конкретного чата
    } else if (obj["type"] == "message") {
        QString chatId = obj["chat_id"].toString();
        QString content = obj["content"].toString();
        QString senderId = obj["sender_id"].toString();
        // Обработка нового сообщения
    }
}


void MainChatWindow::createNewChat() {
    QNetworkAccessManager *manager = new QNetworkAccessManager(this);
    QUrl url(matching_url);
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    initGlobalSettings();

    QString uid = globalSettings->value("uid").toString();
    QString token = globalSettings->value("access_token").toString();

    QJsonObject jsonData;
    jsonData["uid"] = uid;
    jsonData["token"] = token;
    //QMessageBox::information(this, "Cоздание нового чата", uid);
    //QMessageBox::information(this, "Отправка токена", token);

    QJsonDocument doc(jsonData);
    QByteArray postData = doc.toJson();

    QNetworkReply *reply = manager->post(request, postData);
    connect(reply, &QNetworkReply::finished, [=]() {
        if (reply->error() == QNetworkReply::NoError) {
            /*QByteArray responseData = reply->readAll();
            QJsonDocument responseDoc = QJsonDocument::fromJson(responseData);
            QJsonObject responseObj = responseDoc.object();*/
            QMessageBox::information(this, "Cоздание нового чата", "Запрос успешно отправлен, ожиидайте...");
        } else {
            int statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            QByteArray responseData = reply->readAll();
            QJsonDocument responseDoc = QJsonDocument::fromJson(responseData);
            QJsonObject responseObj = responseDoc.object();

            if (statusCode == 500) {
                if (responseObj.contains("detail")) {
                    QString detail = responseObj["detail"].toString();
                    QMessageBox::warning(this, "Создание нового чата", detail);
                } else {
                    QMessageBox::warning(this, "Создание нового чата", "Неизвестная ошибка.");
                }
            } else {
                QMessageBox::warning(this, "Создание нового чата", "Ошибка при отправке данных на сервер: " + reply->errorString());
            }
        }
        reply->deleteLater();
    });
}

void MainChatWindow::filterChats() {
    QString searchText = searchBar->text().trimmed().toLower();

    for (int i = 0; i < chatList->count(); ++i) {
        QListWidgetItem *item = chatList->item(i);
        QString chatName = item->text().toLower();

        if (chatName.contains(searchText)) {
            item->setHidden(false);
        } else {
            item->setHidden(true);
        }
    }
}

