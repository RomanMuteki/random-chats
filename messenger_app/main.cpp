#include <QApplication>
#include "mainwindow.h"

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);

    QIcon appIcon("C:/Users/Romchik/Downloads/1.png");
    app.setWindowIcon(appIcon);

    MainWindow window;
    window.show();
    return app.exec();
}
