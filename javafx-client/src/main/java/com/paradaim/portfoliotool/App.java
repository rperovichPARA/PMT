package com.paradaim.portfoliotool;

import com.paradaim.portfoliotool.service.ApiClient;
import com.paradaim.portfoliotool.ui.MainWindow;
import javafx.application.Application;
import javafx.scene.Scene;
import javafx.stage.Stage;

/**
 * Paradaim Portfolio.Tool Trading V2 - JavaFX Client.
 *
 * Connects to the Python FastAPI backend and provides a full-featured
 * desktop UI for portfolio management and trade execution.
 */
public class App extends Application {

    @Override
    public void start(Stage primaryStage) {
        String apiUrl = getParameters().getNamed().getOrDefault("api", "http://localhost:8000");
        ApiClient client = new ApiClient(apiUrl);

        MainWindow mainWindow = new MainWindow(client, primaryStage);
        Scene scene = new Scene(mainWindow.getRoot(), 1400, 700);
        scene.getStylesheets().add(getClass().getResource("/styles.css").toExternalForm());

        primaryStage.setTitle("Paradaim Portfolio.Tool Trading V2");
        primaryStage.setScene(scene);
        primaryStage.show();

        mainWindow.checkConnection();
    }

    public static void main(String[] args) {
        launch(args);
    }
}
