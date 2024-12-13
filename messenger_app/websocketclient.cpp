#include "websocketclient.h"
#include <QDebug>
#include <QJsonDocument>
#include <QJsonObject>


WebSocketClient::WebSocketClient(QObject *parent) : QObject(parent) {
    m_webSocket = new QWebSocket();
    m_pingTimer = new QTimer(this);

    connect(m_webSocket, &QWebSocket::connected, this, &WebSocketClient::onConnected);
    connect(m_webSocket, &QWebSocket::disconnected, this, &WebSocketClient::onDisconnected);
    connect(m_webSocket, &QWebSocket::textMessageReceived, this, &WebSocketClient::onTextMessageReceived);
    connect(m_pingTimer, &QTimer::timeout, this, &WebSocketClient::sendPing);
}

WebSocketClient::~WebSocketClient() {
    m_webSocket->close();
    delete m_webSocket;
    m_pingTimer->stop();
}

void WebSocketClient::connectToServer(const QUrl &url) {
    m_url = url;
    m_webSocket->open(m_url);
}

void WebSocketClient::sendMessage(const QString &message) {
    if (m_webSocket->state() == QAbstractSocket::ConnectedState) {
        m_webSocket->sendTextMessage(message);
    } else {
        qDebug() << "WebSocket is not connected.";
    }
}

void WebSocketClient::onConnected() {
    qDebug() << "WebSocket connected to" << m_url;
    emit connected();
    m_pingTimer->start(30000);
}

void WebSocketClient::onDisconnected() {
    qDebug() << "WebSocket disconnected from" << m_url;
    qDebug() << "Error:" << m_webSocket->errorString();
    emit disconnected();
    m_pingTimer->stop();
}

void WebSocketClient::onTextMessageReceived(const QString &message) {
    qDebug() << "Message received:" << message;
    emit messageReceived(message);

    QJsonDocument doc = QJsonDocument::fromJson(message.toUtf8());
    QJsonObject obj = doc.object();
    if (obj["type"] == "pong") {
        qDebug() << "Received pong";
    }
}

void WebSocketClient::sendPing() {
    if (m_webSocket->state() == QAbstractSocket::ConnectedState) {
        QJsonObject pingMessage;
        pingMessage["type"] = "ping";
        QJsonDocument doc(pingMessage);
        QString jsonString = QString::fromUtf8(doc.toJson(QJsonDocument::Compact));
        m_webSocket->sendTextMessage(jsonString);
        qDebug() << "Sent ping";
    } else {
        qDebug() << "WebSocket is not connected, cannot send ping.";
    }
}
