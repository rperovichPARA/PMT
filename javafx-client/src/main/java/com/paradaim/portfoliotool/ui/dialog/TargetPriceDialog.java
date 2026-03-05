package com.paradaim.portfoliotool.ui.dialog;

import javafx.geometry.Insets;
import javafx.scene.control.*;
import javafx.scene.layout.*;
import javafx.stage.Stage;

/**
 * Small dialog for editing the target price of a proposed trade.
 */
public class TargetPriceDialog extends Dialog<Double> {

    private Spinner<Integer> priceSpinner;
    private Double result = null;

    public TargetPriceDialog(Stage owner, String symbol, double currentPrice, Double currentTarget) {
        setTitle("Edit Target Price for " + symbol);
        initOwner(owner);

        DialogPane pane = getDialogPane();
        pane.setPrefSize(350, 150);

        VBox content = new VBox(12);
        content.setPadding(new Insets(12));

        content.getChildren().add(new Label(String.format("Current Price: %,.2f JPY", currentPrice)));

        HBox row = new HBox(8);
        row.getChildren().add(new Label("Target Price:"));
        priceSpinner = new Spinner<>(1, 1_000_000, currentTarget != null ? currentTarget.intValue() : 0, 100);
        priceSpinner.setEditable(true);
        priceSpinner.setPrefWidth(150);
        row.getChildren().add(priceSpinner);
        content.getChildren().add(row);

        pane.setContent(content);
        pane.getButtonTypes().addAll(ButtonType.OK, ButtonType.CANCEL);

        Button okBtn = (Button) pane.lookupButton(ButtonType.OK);
        okBtn.setText("Update");
        okBtn.setOnAction(e -> {
            e.consume();
            int val = priceSpinner.getValue();
            if (val <= 0) {
                Alert alert = new Alert(Alert.AlertType.ERROR, "Target Price must be positive");
                alert.showAndWait();
                return;
            }
            result = (double) val;
            close();
        });
    }

    public Double getResult() {
        return result;
    }
}
