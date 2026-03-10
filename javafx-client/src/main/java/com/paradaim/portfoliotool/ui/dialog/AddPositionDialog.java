package com.paradaim.portfoliotool.ui.dialog;

import com.paradaim.portfoliotool.model.StockLookupResult;
import com.paradaim.portfoliotool.service.ApiClient;
import javafx.geometry.Insets;
import javafx.scene.control.*;
import javafx.scene.layout.*;
import javafx.stage.Stage;

import java.text.NumberFormat;
import java.util.*;
import java.util.concurrent.CompletableFuture;

/**
 * Dialog for manually adding a new portfolio position.
 * Supports J-Quants lookup for name, price, ADV, and os_shares.
 * Uses relative average weight instead of raw share quantity.
 */
public class AddPositionDialog extends Dialog<Void> {

    private final ApiClient api;
    private final List<String> fundNames;
    private boolean submitted = false;

    private TextField symbolField;
    private TextField nameField;
    private TextField priceField;
    private TextField advField;
    private CheckBox cashCheck;
    private ToggleGroup currencyGroup;
    private RadioButton jpyRadio;
    private RadioButton usdRadio;
    private Button fetchBtn;
    private Label fetchStatus;
    private double osShares = 0;

    private final Map<String, CheckBox> fundChecks = new LinkedHashMap<>();
    private final Map<String, Spinner<Double>> fundRelWeightInputs = new LinkedHashMap<>();

    public AddPositionDialog(Stage owner, ApiClient api, List<String> fundNames) {
        this.api = api;
        this.fundNames = fundNames;

        setTitle("Add New Position");
        initOwner(owner);
        setResizable(true);

        DialogPane pane = getDialogPane();
        pane.setPrefSize(500, 500);
        pane.setContent(buildContent());
        pane.getButtonTypes().addAll(ButtonType.OK, ButtonType.CANCEL);

        Button okBtn = (Button) pane.lookupButton(ButtonType.OK);
        okBtn.setText("Add");
        okBtn.setOnAction(e -> {
            e.consume();
            onAdd();
        });
    }

    public boolean isSubmitted() {
        return submitted;
    }

    private VBox buildContent() {
        VBox content = new VBox(8);
        content.setPadding(new Insets(12));

        GridPane form = new GridPane();
        form.setHgap(8);
        form.setVgap(8);

        // Row 0: Symbol
        form.add(new Label("Symbol:"), 0, 0);
        symbolField = new TextField();
        symbolField.setPromptText("e.g. 7203");
        form.add(symbolField, 1, 0);

        // Row 1: Name with Fetch Metrics button
        form.add(new Label("Name:"), 0, 1);
        nameField = new TextField();
        HBox nameRow = new HBox(8);
        HBox.setHgrow(nameField, Priority.ALWAYS);
        fetchBtn = new Button("Fetch Metrics");
        fetchBtn.setOnAction(e -> onFetchMetrics());
        nameRow.getChildren().addAll(nameField, fetchBtn);
        form.add(nameRow, 1, 1);

        // Row 2: Price with indicator
        form.add(new Label("Price (JPY):"), 0, 2);
        priceField = new TextField();
        form.add(priceField, 1, 2);

        // Row 3: ADV
        form.add(new Label("10% 3m ADV (USD):"), 0, 3);
        advField = new TextField("0");
        form.add(advField, 1, 3);

        // Row 4: Fetch status
        fetchStatus = new Label("");
        fetchStatus.setStyle("-fx-font-style: italic; -fx-text-fill: #666;");
        form.add(fetchStatus, 0, 4, 2, 1);

        // Row 5: Cash checkbox
        cashCheck = new CheckBox("This is a cash position");
        cashCheck.setOnAction(e -> onCashToggled());
        form.add(cashCheck, 0, 5, 2, 1);

        // Row 6: Currency
        currencyGroup = new ToggleGroup();
        jpyRadio = new RadioButton("JPY");
        jpyRadio.setToggleGroup(currencyGroup);
        jpyRadio.setSelected(true);
        usdRadio = new RadioButton("USD");
        usdRadio.setToggleGroup(currencyGroup);
        HBox currencyBox = new HBox(12, jpyRadio, usdRadio);
        form.add(currencyBox, 0, 6, 2, 1);

        content.getChildren().add(form);

        // Fund rel weights
        TitledPane fundPane = new TitledPane();
        fundPane.setText("Select Funds");
        fundPane.setCollapsible(false);
        VBox fundBox = new VBox(4);
        fundBox.setPadding(new Insets(4));

        for (String fn : fundNames) {
            HBox row = new HBox(8);
            row.setAlignment(javafx.geometry.Pos.CENTER_LEFT);
            CheckBox chk = new CheckBox(fn);
            chk.setSelected(true);
            chk.setPrefWidth(100);
            fundChecks.put(fn, chk);

            Label weightLabel = new Label("Rel. Avg Weight:");
            Spinner<Double> weightSpinner = new Spinner<>(0.0, 10.0, 1.0, 0.01);
            weightSpinner.setEditable(true);
            weightSpinner.setPrefWidth(100);
            // Allow typing decimal values
            weightSpinner.getEditor().textProperty().addListener((obs, oldVal, newVal) -> {
                if (newVal != null && !newVal.isEmpty()) {
                    try {
                        Double.parseDouble(newVal.replace("x", ""));
                    } catch (NumberFormatException ex) {
                        weightSpinner.getEditor().setText(oldVal);
                    }
                }
            });
            fundRelWeightInputs.put(fn, weightSpinner);

            Label xLabel = new Label("x");

            row.getChildren().addAll(chk, weightLabel, weightSpinner, xLabel);
            fundBox.getChildren().add(row);
        }

        fundPane.setContent(fundBox);
        content.getChildren().add(fundPane);

        return content;
    }

    private void onFetchMetrics() {
        String symbol = symbolField.getText().trim();
        if (symbol.isEmpty()) {
            showError("Enter a symbol first");
            return;
        }

        fetchBtn.setDisable(true);
        fetchStatus.setText("Fetching from J-Quants...");

        CompletableFuture.supplyAsync(() -> {
            try {
                return api.stockLookup(symbol);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }).thenAccept(result -> javafx.application.Platform.runLater(() -> {
            fetchBtn.setDisable(false);
            if (result.getName() != null && !result.getName().isEmpty()) {
                nameField.setText(result.getName());
            }
            if (result.getPrice() > 0) {
                priceField.setText(String.valueOf((long) result.getPrice()));
            }
            if (result.getAdv10pct() > 0) {
                advField.setText(NumberFormat.getIntegerInstance().format((long) result.getAdv10pct()));
            }
            osShares = result.getOsShares();

            String statusParts = "Fetched";
            if (osShares > 0) {
                statusParts += " | OS: " + NumberFormat.getIntegerInstance().format((long) osShares);
            }
            fetchStatus.setText(statusParts);
            fetchStatus.setStyle("-fx-font-style: italic; -fx-text-fill: #008800;");
        })).exceptionally(ex -> {
            javafx.application.Platform.runLater(() -> {
                fetchBtn.setDisable(false);
                fetchStatus.setText("Fetch failed: " + ex.getCause().getMessage());
                fetchStatus.setStyle("-fx-font-style: italic; -fx-text-fill: #cc0000;");
            });
            return null;
        });
    }

    private void onCashToggled() {
        if (cashCheck.isSelected()) {
            symbolField.setText("JPY");
            nameField.setText("Japanese Yen");
            priceField.setText("1.0");
            fetchBtn.setDisable(true);
        } else {
            symbolField.clear();
            nameField.clear();
            priceField.clear();
            fetchBtn.setDisable(false);
        }
    }

    private void onAdd() {
        String symbol = symbolField.getText().trim();
        String name = nameField.getText().trim();

        if (symbol.isEmpty()) {
            showError("Symbol is required");
            return;
        }
        if (name.isEmpty()) {
            showError("Name is required");
            return;
        }

        double price;
        try {
            price = Double.parseDouble(priceField.getText().replace(",", ""));
            if (price <= 0) throw new NumberFormatException();
        } catch (NumberFormatException e) {
            showError("Price must be a positive number");
            return;
        }

        double adv;
        try {
            String advText = advField.getText().replace(",", "");
            adv = advText.isEmpty() ? 0 : Double.parseDouble(advText);
        } catch (NumberFormatException e) {
            showError("ADV must be a number");
            return;
        }

        boolean isCash = cashCheck.isSelected();
        String currency = jpyRadio.isSelected() ? "JPY" : "USD";

        Map<String, Double> fundRelWeights = new LinkedHashMap<>();
        for (String fn : fundNames) {
            if (fundChecks.get(fn).isSelected()) {
                double relWeight;
                try {
                    String text = fundRelWeightInputs.get(fn).getEditor().getText().replace("x", "").trim();
                    relWeight = Double.parseDouble(text);
                } catch (NumberFormatException e) {
                    relWeight = fundRelWeightInputs.get(fn).getValue();
                }
                if (relWeight <= 0 && !isCash) {
                    showError("Relative weight for " + fn + " must be positive");
                    return;
                }
                fundRelWeights.put(fn, relWeight);
            }
        }

        if (fundRelWeights.isEmpty()) {
            showError("Select at least one fund");
            return;
        }

        try {
            if (isCash) {
                // Cash positions still use quantity-based flow
                // For cash, interpret rel weight as quantity
                Map<String, Double> fundQuantities = new LinkedHashMap<>();
                for (Map.Entry<String, Double> entry : fundRelWeights.entrySet()) {
                    // Use the spinner value as quantity for cash positions
                    int qty = fundRelWeightInputs.get(entry.getKey()).getValue().intValue();
                    if (qty <= 0) {
                        showError("Quantity for " + entry.getKey() + " must be positive");
                        return;
                    }
                    fundQuantities.put(entry.getKey(), (double) qty);
                }
                api.addPosition(symbol, name, price, true, adv, currency, osShares, fundQuantities);
            } else {
                // New position using rel weights
                api.addPosition(symbol, name, price, false, adv, currency, osShares,
                        new LinkedHashMap<>(), fundRelWeights, true);
            }
            submitted = true;
            close();
        } catch (Exception e) {
            showError("Failed to add position: " + e.getMessage());
        }
    }

    private void showError(String message) {
        Alert alert = new Alert(Alert.AlertType.ERROR, message);
        alert.setHeaderText("Validation Error");
        alert.showAndWait();
    }
}
