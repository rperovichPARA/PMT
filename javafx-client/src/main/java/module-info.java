module com.paradaim.portfoliotool {
    requires javafx.controls;
    requires javafx.fxml;
    requires com.fasterxml.jackson.databind;
    requires com.fasterxml.jackson.core;
    requires okhttp3;
    requires kotlin.stdlib;

    opens com.paradaim.portfoliotool.model to com.fasterxml.jackson.databind;

    exports com.paradaim.portfoliotool;
    exports com.paradaim.portfoliotool.ui;
    exports com.paradaim.portfoliotool.ui.dialog;
    exports com.paradaim.portfoliotool.service;
    exports com.paradaim.portfoliotool.model;
}
