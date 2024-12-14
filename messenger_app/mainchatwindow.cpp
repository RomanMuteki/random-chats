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

    QPalette palette;
    palette.setColor(QPalette::Window, QColor("#E0F0F6"));
    setPalette(palette);
    setAutoFillBackground(true);

    searchBar = new QLabel(this);
    searchBar->setText("Список чатов:");
    searchBar->setStyleSheet(
         "font-weight: bold;"
         "font-style: italic;"
         "font-size: 16px;"
         "font-family: 'Verdana';"
         );

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

    //webSocketClient->connectToServer(QUrl("ws://192.168.243.187:8001/ws/user1"));

    //Запрашиваем список чатов
    //fetchChats();

    connect(chatList, &QListWidget::itemClicked, [this](QListWidgetItem *item) {
        QString chatName = item->text();
        QString chatId = item->data(Qt::UserRole).toString();
        QString recipientId = item->data(Qt::UserRole + 1).toString();
        emit chatSelected(chatName, chatId, recipientId);
    });

    getWebSocketHandler();
}


void MainChatWindow::fetchChats() {
    // Отправляем запрос на получение списка чатов
    QJsonObject request;
    request["type"] = "fetch_chats";
    QJsonDocument doc(request);
    QString jsonString = QString::fromUtf8(doc.toJson(QJsonDocument::Compact));
    webSocketClient->sendMessage(jsonString);
}


void MainChatWindow::allChatsHendler(const QJsonArray &chats) {
    chatList->clear();
    for (const QJsonValue &chat : chats) {
        QJsonObject chatObj = chat.toObject();
        QString chatId = chatObj["_id"].toString();
        QString recipientId = "Unknown";
        QString recipient1Id = chatObj["participants"].toArray().first().toString();
        QString recipient2Id = chatObj["participants"].toArray().last().toString();
        QString uid = globalSettings->value("uid").toString();
        QString chatName = "";
        QString lastMessageContent = "";
                 if (chatObj.contains("last_message") && chatObj["last_message"].isObject()) {
                     QJsonObject lastMessageObj = chatObj["last_message"].toObject();
                     lastMessageContent = lastMessageObj["content"].toString();
                 }
        if (recipient1Id != uid) {
            recipientId = recipient1Id;
            chatName = recipient1Id + ": " + lastMessageContent;
        } else if (recipient2Id != uid) {
            recipientId = recipient2Id;
            chatName = recipient2Id + ": " + lastMessageContent;
        } else {
            chatName = recipientId + ": " + lastMessageContent;
        }

        QListWidgetItem *item = new QListWidgetItem(chatName, chatList);
        item->setData(Qt::UserRole, chatId);
        item->setData(Qt::UserRole + 1, recipientId);
        item->setBackground(QColor(255, 255, 255, 100));
        item->setForeground(Qt::black);
        item->setFont(QFont("Arial", 12, QFont::Bold));
        item->setSizeHint(QSize(0, 50));

        // Создаем виджет с эффектом тени
        QWidget *widget = new QWidget;
        QVBoxLayout *layout = new QVBoxLayout(widget);
        QLabel *label = new QLabel(chatName, widget);
        layout->addWidget(label);

        QGraphicsDropShadowEffect *shadowEffect = new QGraphicsDropShadowEffect;
        shadowEffect->setBlurRadius(10);
        shadowEffect->setColor(QColor(0, 0, 0, 50));
        shadowEffect->setOffset(2, 2);
        label->setGraphicsEffect(shadowEffect);

        chatList->setItemWidget(item, widget);
    }
}


void MainChatWindow::allMessagesHendller(const QJsonArray &messages) {
    // Создаем карту для хранения сообщений по chat_id
    QMap<QString, QJsonArray> chatMessagesMap;

    // Проходим по всем сообщениям и распределяем их по chat_id
    for (const QJsonValue &message : messages) {
        QJsonObject messageObj = message.toObject();
        QString chatId = messageObj["chat_id"].toString();

        // Если для этого chat_id еще нет массива сообщений, создаем его
        if (!chatMessagesMap.contains(chatId)) {
            chatMessagesMap[chatId] = QJsonArray();
        }

        // Добавляем текущее сообщение в соответствующий массив
        chatMessagesMap[chatId].append(messageObj);
    }

    // После того как все сообщения распределены по чатам, отправляем их в updateMessagesForChat
    for (auto it = chatMessagesMap.begin(); it != chatMessagesMap.end(); ++it) {
        QString chatId = it.key();
        QJsonArray chatMessages = it.value();
        updateMessagesForChat(chatId, chatMessages);
    }
}


void MainChatWindow::newChatsHendler(const QJsonArray &newChats) {
    for (const QJsonValue &chat : newChats) {
        QJsonObject chatObj = chat.toObject();
        QString chatId = chatObj["_id"].toString();
        QString recipientId = "Unknown";
        QString recipient1Id = chatObj["participants"].toArray().first().toString();
        QString recipient2Id = chatObj["participants"].toArray().last().toString();
        QString uid = globalSettings->value("uid").toString();
        QString chatName = "";
        QString lastMessageContent = "";
                 if (chatObj.contains("last_message") && chatObj["last_message"].isObject()) {
                     QJsonObject lastMessageObj = chatObj["last_message"].toObject();
                     lastMessageContent = lastMessageObj["content"].toString();
                 }
        if (recipient1Id != uid) {
            recipientId = recipient1Id;
            chatName = recipient1Id + ": " + lastMessageContent;
        } else if (recipient2Id != uid) {
            recipientId = recipient2Id;
            chatName = recipient2Id + ": " + lastMessageContent;
        } else {
            chatName = recipientId + ": " + lastMessageContent;
        }

        QListWidgetItem *item = new QListWidgetItem(chatName, chatList);
        item->setData(Qt::UserRole, chatId);
        item->setData(Qt::UserRole + 1, recipientId);
        item->setBackground(QColor(255, 255, 255, 100));
        item->setForeground(Qt::black);
        item->setFont(QFont("Arial", 12, QFont::Bold));
        item->setSizeHint(QSize(0, 50));

        // Создаем виджет с эффектом тени
        QWidget *widget = new QWidget;
        QVBoxLayout *layout = new QVBoxLayout(widget);
        QLabel *label = new QLabel(chatName, widget);
        layout->addWidget(label);

        QGraphicsDropShadowEffect *shadowEffect = new QGraphicsDropShadowEffect;
        shadowEffect->setBlurRadius(10);
        shadowEffect->setColor(QColor(0, 0, 0, 50));
        shadowEffect->setOffset(2, 2);
        label->setGraphicsEffect(shadowEffect);

        chatList->setItemWidget(item, widget);
    }
}


void MainChatWindow::onMessageReceived(const QString &message) {
    QJsonDocument doc = QJsonDocument::fromJson(message.toUtf8());
    QJsonObject obj = doc.object();

    if (obj["type"] == "all_chats") {
        QJsonArray chats = obj["data"].toArray();
        allChatsHendler(chats);
    }
    else if (obj["type"] == "all_messages") {
        QJsonArray messages = obj["data"].toArray();
        allMessagesHendller(messages);
    }
    else if (obj["type"] == "new_chats") {
        QJsonArray newChats = obj["data"].toArray();
        newChatsHendler(newChats);

    } else if (obj["type"] == "message") {
        QString chatId = obj["chat_id"].toString();
        QString senderId = obj["sender_id"].toString();
        QString content = obj["content"].toString();
        QString messageId = obj["message_id"].toString();
        QString timestamp = obj["timestamp"].toString();

        // Создаем объект для одного сообщения
        QJsonObject messageObj;
        messageObj["chat_id"] = chatId;
        messageObj["sender_id"] = senderId;
        messageObj["content"] = content;
        messageObj["message_id"] = messageId;
        messageObj["timestamp"] = timestamp;

        // Создаем массив с этим сообщением
        QJsonArray messagesArray;
        messagesArray.append(messageObj);

        // Отправляем запрос в updateMessagesForChat с этим массивом
        updateMessagesForChat(chatId, messagesArray);
    }
}

// void MainChatWindow::updateMessagesForChat(const QString &chatId, const QJsonArray &messages) {

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


void MainChatWindow::getWebSocketHandler() {
    // Получаем uid и token из глобальных настроек
    QString uid = globalSettings->value("uid").toString();
    QString token = globalSettings->value("access_token").toString();

    // Создаём менеджер для сетевых запросов
    QNetworkAccessManager *manager = new QNetworkAccessManager(this);

    // URL для запроса
    QUrl url("http://212.34.139.173:8500/get_websocket_handler");
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    // Подготовка данных для POST-запроса
    QJsonObject jsonData;
    jsonData["uid"] = uid;
    jsonData["token"] = token;

    QJsonDocument doc(jsonData);
    QByteArray postData = doc.toJson();

    // Отправляем POST-запрос
    QNetworkReply *reply = manager->post(request, postData);

    // Обрабатываем ответ
    connect(reply, &QNetworkReply::finished, [this, reply]() {
        if (reply->error() == QNetworkReply::NoError) {
            QByteArray responseData = reply->readAll();
            QJsonDocument responseDoc = QJsonDocument::fromJson(responseData);
            QJsonObject responseObj = responseDoc.object();

            // Проверяем, что получены необходимые данные
            if (responseObj.contains("websocket_handler_url") && responseObj.contains("handler_id")) {
                QString handlerUrl = responseObj["websocket_handler_url"].toString();
                QString handlerId = responseObj["handler_id"].toString();

                // Преобразуем http в ws для URL WebSocket
                if (handlerUrl.startsWith("http://")) {
                    handlerUrl.replace(0, 4, "ws");
                }

                // Сохраняем данные в глобальные настройки
                globalSettings->setValue("websocket_handler_url", handlerUrl);
                globalSettings->setValue("handler_id", handlerId);
                globalSettings->sync();

                qDebug() << "WebSocket handler URL:" << handlerUrl;
                qDebug() << "Handler ID:" << handlerId;

                // Подключаемся к WebSocket серверу
                webSocketClient->connectToServer(QUrl(handlerUrl), globalSettings->value("uid").toString(), globalSettings->value("access_token").toString());
            } else {
                qDebug() << "Ошибка: не удалось получить websocket_handler_url или handler_id.";
            }
        } else {
            qDebug() << "Ошибка при запросе websocket handler:" << reply->errorString();
        }

        // Освобождаем ресурсы
        reply->deleteLater();
    });
}



void MainChatWindow::filterChats() {
    QString searchText = searchBar->text().trimmed().toLower();

    // Проходим по всем элементам списка чатов
    for (int i = 0; i < chatList->count(); ++i) {
        QListWidgetItem *item = chatList->item(i);
        QString chatName = item->text().toLower();  // Приводим имя чата к нижнему регистру для нечувствительного поиска

        // Если имя чата содержит текст поиска, показываем его, иначе скрываем
        if (chatName.contains(searchText)) {
            item->setHidden(false);
        } else {
            item->setHidden(true);
        }
    }
}



void MainChatWindow::updateMessagesForChat(const QString &chatId, const QJsonArray &messages) {
    // Сортируем сообщения по времени (timestamp)
    QList<QJsonObject> sortedMessages;
    for (const QJsonValue &message : messages) {
        sortedMessages.append(message.toObject());
    }

    // Сортируем по timestamp
    std::sort(sortedMessages.begin(), sortedMessages.end(), [](const QJsonObject &a, const QJsonObject &b) {
        QString timestampA = a["timestamp"].toString();
        QString timestampB = b["timestamp"].toString();
        return timestampA < timestampB;  // Сортировка по строке (timestamp)
    });

    // Проходим по отсортированным сообщениям и отображаем их
    for (const QJsonObject &messageObj : sortedMessages) {
        // Проверяем наличие нужных полей
        QString senderId = messageObj.contains("sender_id") ? messageObj["sender_id"].toString() : "Unknown";
        QString content = messageObj.contains("content") ? messageObj["content"].toString() : "";
        QString timestamp = messageObj.contains("timestamp") ? messageObj["timestamp"].toString() : "";

        // Логирование сообщения в консоль
        qDebug() << "New message in chat" << chatId << "from" << senderId << ":" << content;

        // Найдем соответствующий чат в списке чатов
        for (int i = 0; i < chatList->count(); ++i) {
            QListWidgetItem *item = chatList->item(i);
            QString currentChatId = item->data(Qt::UserRole).toString();
            if (currentChatId == chatId) {
                // Создаем новый элемент для отображения сообщения
                QString messageText = senderId + ": " + content + " (" + timestamp + ")";
                QListWidgetItem *messageItem = new QListWidgetItem(messageText, item->listWidget());
                messageItem->setBackground(QColor(230, 230, 230));
                messageItem->setFont(QFont("Arial", 10));
                messageItem->setSizeHint(QSize(0, 40));

                // Добавляем сообщение в чат (перед этим должно быть что-то вроде QListWidget для сообщений в чате)
                item->listWidget()->addItem(messageItem);
                break;
            }
        }
    }
}






// #include "mainchatwindow.h"
// #include <QVBoxLayout>
// #include <QHBoxLayout>
// #include <QLabel>
// #include <QPushButton>
// #include <QLineEdit>
// #include <QListWidget>
// #include <QPalette>
// #include <QColor>
// #include <QFont>
// #include <QGraphicsDropShadowEffect>
// #include <QJsonArray>
// #include <QJsonObject>
// #include <QJsonDocument>
// #include <QMessageBox>
// #include <QNetworkAccessManager>
// #include <QNetworkRequest>
// #include <QNetworkReply>
// #include <QSettings>
// #include "websocketclient.h"
// #include "loginform.h"

// MainChatWindow::MainChatWindow(QWidget *parent) : QWidget(parent) {
//     QVBoxLayout *mainLayout = new QVBoxLayout(this);

//     //setFixedSize(600,400);
//     QPalette palette;
//     palette.setColor(QPalette::Window, QColor("#E0F0F6"));
//     setPalette(palette);
//     setAutoFillBackground(true);

//     searchBar = new QLabel(this);
//     searchBar->setText("Список чатов:");
//     searchBar->setStyleSheet(
//         "font-weight: bold;"
//         "font-style: italic;"
//         "font-size: 16px;"
//         "font-family: 'Verdana';"
//         );
//     mainLayout->addWidget(searchBar);
//     //connect(searchBar, &QLineEdit::textChanged, this, &MainChatWindow::filterChats);

//     chatList = new QListWidget(this);
//     chatList->setStyleSheet("QListWidget { border: 1px solid #ccc; border-radius: 5px; padding: 5px; background: rgba(255, 255, 255, 0.8); }"
//                             "QListWidget::item { padding: 10px; border: 1px solid #ddd; border-radius: 5px; margin: 5px; }"
//                             "QListWidget::item:selected { background: #007BFF; color: white; border: 1px solid #0056b3; }");
//     mainLayout->addWidget(chatList);


//     addChatButton = new QPushButton("+", this);
//     QFont font = addChatButton->font();
//     font.setBold(true);
//     addChatButton->setFont(font);
//     addChatButton->setStyleSheet("QPushButton {color: black; border: none; border-radius: 50%; font-size: 24px; padding: 10px; }"
//                                  "QPushButton:hover { background: #0056b3; }"
//                                  "QPushButton:pressed { background: #6C757D; }");
//     addChatButton->setFixedSize(50, 50);
//     connect(addChatButton, &QPushButton::clicked, this, &MainChatWindow::createNewChat);

//     QHBoxLayout *buttonLayout = new QHBoxLayout();
//     buttonLayout->addStretch();
//     buttonLayout->addWidget(addChatButton);
//     mainLayout->addLayout(buttonLayout);

//     setLayout(mainLayout);

//     webSocketClient = new WebSocketClient(this);
//     connect(webSocketClient, &WebSocketClient::messageReceived, this, &MainChatWindow::onMessageReceived);

//     //webSocketClient->connectToServer(QUrl("ws://192.168.243.187:8001/ws/user1"));

//     //Запрашиваем список чатов
//     //fetchChats();

//     connect(chatList, &QListWidget::itemClicked, [this](QListWidgetItem *item) {
//         QString chatName = item->text();
//         QString chatId = item->data(Qt::UserRole).toString();
//         QString recipientId = item->data(Qt::UserRole + 1).toString();
//         emit chatSelected(chatName, chatId, recipientId);
//     });
//     getWebSocketHandler();
// }

// void MainChatWindow::fetchChats() {
//     // Отправляем запрос на получение списка чатов
//     QJsonObject request;
//     request["type"] = "fetch_chats";
//     QJsonDocument doc(request);
//     QString jsonString = QString::fromUtf8(doc.toJson(QJsonDocument::Compact));
//     webSocketClient->sendMessage(jsonString);
// }


// void MainChatWindow::updateChatList (const QJsonArray &chats) {
//     chatList->clear();
//     for (const QJsonValue &chat : chats) {
//         QJsonObject chatObj = chat.toObject();
//         QString chatId = chatObj["_id"].toString();
//         QString recipientId = "Unknown";
//         QString recipient1Id = chatObj["participants"].toArray().first().toString();
//         QString recipient2Id = chatObj["participants"].toArray().last().toString();
//         QString uid = globalSettings->value("uid").toString();
//         QString chatName = "";
//         // Проверяем, существует ли last_message
//         QString lastMessageContent = "";
//         if (chatObj.contains("last_message") && chatObj["last_message"].isObject()) {
//             QJsonObject lastMessageObj = chatObj["last_message"].toObject();
//             lastMessageContent = lastMessageObj["content"].toString();
//         }

//         // Определяем recipientId и chatName
//         if (recipient1Id != uid) {
//             recipientId = recipient1Id;
//             chatName = recipient1Id + ": " + lastMessageContent;
//         } else if (recipient2Id != uid) {
//             recipientId = recipient2Id;
//             chatName = recipient2Id + ": " + lastMessageContent;
//         } else {
//             chatName = recipientId + ": " + lastMessageContent;
//         }




//         QListWidgetItem *item = new QListWidgetItem(chatName, chatList);
//         item->setData(Qt::UserRole, chatId);
//         item->setData(Qt::UserRole + 1, recipientId);
//         item->setBackground(QColor(255, 255, 255, 100));
//         item->setForeground(Qt::black);
//         item->setFont(QFont("Arial", 12, QFont::Bold));
//         item->setSizeHint(QSize(0, 50));

//         QGraphicsDropShadowEffect *shadowEffect = new QGraphicsDropShadowEffect;
//         shadowEffect->setBlurRadius(10);
//         shadowEffect->setColor(QColor(0, 0, 0, 50));
//         shadowEffect->setOffset(2, 2);
//         chatList->setItemWidget(item, new QWidget);
//         chatList->itemWidget(item)->setGraphicsEffect(shadowEffect);
//     }
// }

// void MainChatWindow::onMessageReceived(const QString &message) {
//     QJsonDocument doc = QJsonDocument::fromJson(message.toUtf8());
//     QJsonObject obj = doc.object();

//     if (obj["type"] == "all_chats") {
//         QJsonArray chats = obj["data"].toArray();
//         updateChatList(chats);
//     } else if (obj["type"] == "new_chats") {
//         QJsonArray newChats = obj["data"].toArray();
//         for (const QJsonValue &chat : newChats) {
//             QJsonObject chatObj = chat.toObject();
//             QString chatName = chatObj["name"].toString();
//             QString chatId = chatObj["_id"].toString();
//             QString recipientId = chatObj["participants"].toArray().first().toString();

//             QListWidgetItem *item = new QListWidgetItem(chatName, chatList);
//             item->setData(Qt::UserRole, chatId);
//             item->setData(Qt::UserRole + 1, recipientId);
//             item->setBackground(QColor(255, 255, 255, 100));
//             item->setForeground(Qt::black);
//             item->setFont(QFont("Arial", 12, QFont::Bold));
//             item->setSizeHint(QSize(0, 50));

//             QGraphicsDropShadowEffect *shadowEffect = new QGraphicsDropShadowEffect;
//             shadowEffect->setBlurRadius(10);
//             shadowEffect->setColor(QColor(0, 0, 0, 50));
//             shadowEffect->setOffset(2, 2);
//             chatList->setItemWidget(item, new QWidget);
//             chatList->itemWidget(item)->setGraphicsEffect(shadowEffect);
//         }
//     } else if (obj["type"] == "all_messages" || obj["type"] == "new_messages") {
//         QString chatId = obj["chat_id"].toString();
//         QJsonArray messages = obj["data"].toArray();
//         updateMessagesForChat(chatId, messages);
//     } else if (obj["type"] == "message") {
//         QString chatId = obj["chat_id"].toString();
//         QString senderId = obj["sender_id"].toString();
//         QString content = obj["content"].toString();
//         QString messageId = obj["message_id"].toString();
//         QString timestamp = obj["timestamp"].toString();
//     }
// }


// void MainChatWindow::createNewChat() {
//     QNetworkAccessManager *manager = new QNetworkAccessManager(this);
//     QUrl url(matching_url);
//     QNetworkRequest request(url);
//     request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
//     initGlobalSettings();

//     QString uid = globalSettings->value("uid").toString();
//     QString token = globalSettings->value("access_token").toString();

//     QJsonObject jsonData;
//     jsonData["uid"] = uid;
//     jsonData["token"] = token;
//     //QMessageBox::information(this, "Cоздание нового чата", uid);
//     //QMessageBox::information(this, "Отправка токена", token);

//     QJsonDocument doc(jsonData);
//     QByteArray postData = doc.toJson();

//     QNetworkReply *reply = manager->post(request, postData);
//     connect(reply, &QNetworkReply::finished, [=]() {
//         if (reply->error() == QNetworkReply::NoError) {
//             /*QByteArray responseData = reply->readAll();
//             QJsonDocument responseDoc = QJsonDocument::fromJson(responseData);
//             QJsonObject responseObj = responseDoc.object();*/
//             QMessageBox::information(this, "Cоздание нового чата", "Запрос успешно отправлен, ожиидайте...");
//         } else {
//             int statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
//             QByteArray responseData = reply->readAll();
//             QJsonDocument responseDoc = QJsonDocument::fromJson(responseData);
//             QJsonObject responseObj = responseDoc.object();

//             if (statusCode == 500) {
//                 if (responseObj.contains("detail")) {
//                     QString detail = responseObj["detail"].toString();
//                     QMessageBox::warning(this, "Создание нового чата", detail);
//                 } else {
//                     QMessageBox::warning(this, "Создание нового чата", "Неизвестная ошибка.");
//                 }
//             } else {
//                 QMessageBox::warning(this, "Создание нового чата", "Ошибка при отправке данных на сервер: " + reply->errorString());
//             }
//         }
//         reply->deleteLater();
//     });
// }

// void MainChatWindow::getWebSocketHandler() {
//     // Получаем uid и token из глобальных настроек
//     QString uid = globalSettings->value("uid").toString();
//     QString token = globalSettings->value("access_token").toString();

//     QNetworkAccessManager *manager = new QNetworkAccessManager(this);
//     QUrl url("http://212.34.139.173:8500/get_websocket_handler");
//     QNetworkRequest request(url);
//     request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

//     QJsonObject jsonData;
//     jsonData["uid"] = uid;
//     jsonData["token"] = token;

//     QJsonDocument doc(jsonData);
//     QByteArray postData = doc.toJson();

//     QNetworkReply *reply = manager->post(request, postData);
//     connect(reply, &QNetworkReply::finished, [=]() {
//         if (reply->error() == QNetworkReply::NoError) {
//             QByteArray responseData = reply->readAll();
//             QJsonDocument responseDoc = QJsonDocument::fromJson(responseData);
//             QJsonObject responseObj = responseDoc.object();

//             if (responseObj.contains("websocket_handler_url") && responseObj.contains("handler_id")) {
//                 QString handlerUrl = responseObj["websocket_handler_url"].toString();
//                 QString handlerId = responseObj["handler_id"].toString();

//                 if (handlerUrl.startsWith("http://")) {
//                     handlerUrl.replace(0, 4, "ws");
//                 }

//                 globalSettings->setValue("websocket_handler_url", handlerUrl);
//                 globalSettings->setValue("handler_id", handlerId);
//                 globalSettings->sync();

//                 qDebug() << "WebSocket handler URL:" << handlerUrl;
//                 qDebug() << "Handler ID:" << handlerId;

//                 webSocketClient->connectToServer(QUrl(handlerUrl), uid, token);
//                 //fetchChats();
//                 //webSocketClient->sendPing();

//             } else {
//                 qDebug() << "Ошибка: не удалось получить websocket_handler_url или handler_id.";
//             }
//         } else {
//             qDebug() << "Ошибка при запросе websocket handler:" << reply->errorString();
//         }
//         reply->deleteLater();
//     });
// }





// void MainChatWindow::filterChats() {
//     QString searchText = searchBar->text().trimmed().toLower();

//     for (int i = 0; i < chatList->count(); ++i) {
//         QListWidgetItem *item = chatList->item(i);
//         QString chatName = item->text().toLower();

//         if (chatName.contains(searchText)) {
//             item->setHidden(false);
//         } else {
//             item->setHidden(true);
//         }
//     }
// }

// void MainChatWindow::updateMessagesForChat(const QString &chatId, const QJsonArray &messages) {
//     for (const QJsonValue &message : messages) {
//         QJsonObject messageObj = message.toObject();
//         QString senderId = messageObj["sender_id"].toString();
//         QString content = messageObj["content"].toString();
//         QString timestamp = messageObj["timestamp"].toString();

//         // Пример: добавление сообщения в интерфейс
//         qDebug() << "New message in chat" << chatId << "from" << senderId << ":" << content;
//     }
// }
