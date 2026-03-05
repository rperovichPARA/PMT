package com.paradaim.portfoliotool.ui.dialog;

import com.paradaim.portfoliotool.model.*;
import com.paradaim.portfoliotool.service.ApiClient;
import javafx.geometry.Insets;
import javafx.scene.control.*;
import javafx.scene.layout.*;
import javafx.stage.Stage;

import java.text.NumberFormat;
import java.util.*;

/**
 * Multi-fund trade proposal dialog.
 * Allows setting a new relative weight per fund and previewing the resulting trade.
 */
public class TradeDialog extends Dialog<Void> {

    private final ApiClient api;
    private final PositionData position;
    private final List<String> fundNames;
    private boolean submitted = false;

    private final Map<String, Spinner<Double>> rawInputs = new LinkedHashMap<>();
    private final Map<String, Label> tradeTypeLabels = new LinkedHashMap<>();
    private final Map<String, Label> sharesLabels = new LinkedHashMap<>();
    private final Map<String, Label> usdLabels = new LinkedHashMap<>();
    private final Map<String, TradeResult> calculatedTrades = new LinkedHashMap<>();

    private Label newPctLabel;
    private Label changePctLabel;

    private static final String[][] FUND_COLORS = {
        {"230", "242", "255"},  // Light blue
        {"230", "255", "230"},  // Light green
        {"255", "242", "230"},  // Light orange
        {"242", "230", "255"},  // Light purple
    };

    public TradeDialog(Stage owner, ApiClient api, PositionData position, List<String> fundNames) {
        this.api = api;
        this.position = position;
        this.fundNames = fundNames;

        setTitle("Create Trade for " + position.getSymbol());
        initOwner(owner);
        setResizable(true);

        DialogPane pane = getDialogPane();
        pane.setPrefSize(600, 500);
        pane.setContent(buildContent());
        pane.getButtonTypes().addAll(ButtonType.OK, ButtonType.CANCEL);

        Button okBtn = (Button) pane.lookupButton(ButtonType.OK);
        okBtn.setText("Submit");
        okBtn.setOnAction(e -> {
            e.consume();
            submitTrades();
        });
    }

    public boolean isSubmitted() {
        return submitted;
    }

    private VBox buildContent() {
        VBox content = new VBox(12);
        content.setPadding(new Insets(12));

        // Header info
        VBox header = new VBox(4);
        header.getChildren().add(new Label(String.format(
                "Symbol: %s    Name: %s    Price: %,.2f JPY",
                position.getSymbol(), position.getName(), position.getPrice())));

        HBox pctRow = new HBox(16);
        pctRow.getChildren().add(new Label(String.format(
                "Current %% of Company: %.2f%%", position.getTotalPctOfCompany() * 100)));
        newPctLabel = new Label("New % of Company: -");
        changePctLabel = new Label("Change %: -");
        pctRow.getChildren().addAll(newPctLabel, changePctLabel);
        header.getChildren().add(pctRow);
        content.getChildren().add(header);

        // Per-fund entries
        ScrollPane scroll = new ScrollPane();
        scroll.setFitToWidth(true);
        VBox fundBox = new VBox(8);

        for (int i = 0; i < fundNames.size(); i++) {
            String fundName = fundNames.get(i);
            FundPositionData fp = position.getFunds() != null ? position.getFunds().get(fundName) : null;
            if (fp == null) continue;

            double currentRaw = fp.getRelWeight();
            String[] color = FUND_COLORS[i % FUND_COLORS.length];

            VBox fundEntry = new VBox(4);
            fundEntry.setPadding(new Insets(8));
            fundEntry.setStyle(String.format(
                    "-fx-background-color: rgba(%s, %s, %s, 0.3); -fx-border-color: #d0d0d0; -fx-border-radius: 4;",
                    color[0], color[1], color[2]));

            Label fundLabel = new Label(fundName);
            fundLabel.setStyle("-fx-font-weight: bold; -fx-font-size: 13px;");

            GridPane grid = new GridPane();
            grid.setHgap(12);
            grid.setVgap(4);

            grid.add(new Label("Current Rel. Weight:"), 0, 0);
            grid.add(new Label(String.format("%.2fx", currentRaw)), 1, 0);

            grid.add(new Label("New Rel. Weight:"), 0, 1);
            Spinner<Double> rawInput = new Spinner<>(0.0, 10.0, currentRaw, 0.01);
            rawInput.setEditable(true);
            rawInput.setPrefWidth(100);
            rawInputs.put(fundName, rawInput);
            grid.add(rawInput, 1, 1);

            grid.add(new Label("USD Value:"), 2, 1);
            Label usdLabel = new Label("");
            usdLabels.put(fundName, usdLabel);
            grid.add(usdLabel, 3, 1);

            grid.add(new Label("Trade Type:"), 0, 2);
            Label typeLabel = new Label("");
            tradeTypeLabels.put(fundName, typeLabel);
            grid.add(typeLabel, 1, 2);

            grid.add(new Label("Shares:"), 2, 2);
            Label sharesLabel = new Label("");
            sharesLabels.put(fundName, sharesLabel);
            grid.add(sharesLabel, 3, 2);

            String fn = fundName;
            rawInput.valueProperty().addListener((obs, old, val) -> onRawChanged(fn));

            fundEntry.getChildren().addAll(fundLabel, grid);
            fundBox.getChildren().add(fundEntry);
        }

        scroll.setContent(fundBox);
        VBox.setVgrow(scroll, Priority.ALWAYS);
        content.getChildren().add(scroll);

        return content;
    }

    private void onRawChanged(String fundName) {
        double newRaw = rawInputs.get(fundName).getValue();
        FundPositionData fp = position.getFunds().get(fundName);
        if (fp == null) return;

        double currentRaw = fp.getRelWeight();
        if (Math.abs(newRaw - currentRaw) < 0.001) {
            tradeTypeLabels.get(fundName).setText("");
            sharesLabels.get(fundName).setText("");
            usdLabels.get(fundName).setText("");
            clearStyle(fundName);
            calculatedTrades.remove(fundName);
            return;
        }

        try {
            TradeResult result = api.calculateTrade(fundName, position.getSymbol(), newRaw);
            calculatedTrades.put(fundName, result);

            String color = "Buy".equals(result.getTradeType()) ? "#008800" : "#cc0000";
            String style = "-fx-text-fill: " + color + "; -fx-font-weight: bold;";

            tradeTypeLabels.get(fundName).setText(result.getTradeType());
            tradeTypeLabels.get(fundName).setStyle(style);

            sharesLabels.get(fundName).setText(formatNumber(result.getTradeQuantity()));
            sharesLabels.get(fundName).setStyle(style);

            usdLabels.get(fundName).setText(formatNumber(Math.abs(result.getTradeValueUsd())) + " USD");
            usdLabels.get(fundName).setStyle(style);
        } catch (Exception e) {
            clearStyle(fundName);
            calculatedTrades.remove(fundName);
        }
    }

    private void clearStyle(String fundName) {
        tradeTypeLabels.get(fundName).setStyle("");
        sharesLabels.get(fundName).setStyle("");
        usdLabels.get(fundName).setStyle("");
    }

    private void submitTrades() {
        boolean anySubmitted = false;

        for (Map.Entry<String, TradeResult> entry : calculatedTrades.entrySet()) {
            String fundName = entry.getKey();
            TradeResult result = entry.getValue();
            double targetRaw = rawInputs.get(fundName).getValue();

            if (Math.abs(result.getTradeQuantity()) < 1) continue;

            try {
                api.submitTrade(fundName, position.getSymbol(), result.getTradeType(),
                        targetRaw, result.getTradeQuantity(), result.getTradeValueUsd());
                anySubmitted = true;
            } catch (Exception e) {
                Alert alert = new Alert(Alert.AlertType.ERROR,
                        "Failed to submit trade for " + fundName + ": " + e.getMessage());
                alert.showAndWait();
            }
        }

        if (anySubmitted) {
            submitted = true;
            close();
        }
    }

    private static String formatNumber(double value) {
        return NumberFormat.getIntegerInstance().format((long) value);
    }
}
