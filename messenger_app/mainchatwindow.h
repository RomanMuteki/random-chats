#ifndef MAINCHATWINDOW_H
#define MAINCHATWINDOW_H

#include <QWidget>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>

class MainChatWindow : public QWidget {
    Q_OBJECT

public:
    explicit MainChatWindow(QWidget *parent = nullptr);

signals:
    void chatSelected(const QString &chatName);

private:
    QLineEdit *searchBar;
    QListWidget *chatList;
    QPushButton *addChatButton;
};

#endif // MAINCHATWINDOW_H
