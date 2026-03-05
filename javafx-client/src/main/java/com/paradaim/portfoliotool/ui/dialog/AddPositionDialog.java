package com.paradaim.portfoliotool.ui.dialog;

import com.paradaim.portfoliotool.service.ApiClient;
import javafx.geometry.Insets;
import javafx.scene.control.*;
import javafx.scene.layout.*;
import javafx.stage.Stage;

import java.util.*;

/**
 * Dialog for manually adding a new portfolio position.
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
    private final Map<String, CheckBox> fundChecks = new LinkedHashMap<>();
    private final Map<String, Spinner<Integer>> fundQtyInputs = new LinkedHashMap<>();

    public AddPositionDialog(Stage owner, ApiClient api, List<String> fundNames) {
        this.api = api;
        this.fundNames = fundNames;

        setTitle("Add New Position");
        initOwner(owner);
        setResizable(true);

        DialogPane pane = getDialogPane();
        pane.setPrefSize(400, 450);
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

        form.add(new Label("Symbol:"), 0, 0);
        symbolField = new TextField();
        form.add(symbolField, 1, 0);

        form.add(new Label("Name:"), 0, 1);
        nameField = new TextField();
        form.add(nameField, 1, 1);

        form.add(new Label("Price (JPY):"), 0, 2);
        priceField = new TextField();
        form.add(priceField, 1, 2);

        form.add(new Label("10% 3m ADV (USD):"), 0, 3);
        advField = new TextField("0");
        form.add(advField, 1, 3);

        cashCheck = new CheckBox("This is a cash position");
        cashCheck.setOnAction(e -> onCashToggled());
        form.add(cashCheck, 0, 4, 2, 1);

        currencyGroup = new ToggleGroup();
        jpyRadio = new RadioButton("JPY");
        jpyRadio.setToggleGroup(currencyGroup);
        jpyRadio.setSelected(true);
        usdRadio = new RadioButton("USD");
        usdRadio.setToggleGroup(currencyGroup);
        HBox currencyBox = new HBox(12, jpyRadio, usdRadio);
        form.add(currencyBox, 0, 5, 2, 1);

        content.getChildren().add(form);

        // Fund quantities
        TitledPane fundPane = new TitledPane();
        fundPane.setText("Select Funds");
        fundPane.setCollapsible(false);
        VBox fundBox = new VBox(4);
        fundBox.setPadding(new Insets(4));

        for (String fn : fundNames) {
            HBox row = new HBox(8);
            CheckBox chk = new CheckBox(fn);
            chk.setSelected(true);
            chk.setPrefWidth(100);
            fundChecks.put(fn, chk);

            Label qtyLabel = new Label("Quantity:");
            Spinner<Integer> qty = new Spinner<>(0, 100_000_000, 0, 100);
            qty.setEditable(true);
            qty.setPrefWidth(120);
            fundQtyInputs.put(fn, qty);

            row.getChildren().addAll(chk, qtyLabel, qty);
            fundBox.getChildren().add(row);
        }

        fundPane.setContent(fundBox);
        content.getChildren().add(fundPane);

        return content;
    }

    private void onCashToggled() {
        if (cashCheck.isSelected()) {
            symbolField.setText("JPY");
            nameField.setText("Japanese Yen");
            priceField.setText("1.0");
        } else {
            symbolField.clear();
            nameField.clear();
            priceField.clear();
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
            price = Double.parseDouble(priceField.getText());
            if (price <= 0) throw new NumberFormatException();
        } catch (NumberFormatException e) {
            showError("Price must be a positive number");
            return;
        }

        double adv;
        try {
            adv = advField.getText().isEmpty() ? 0 : Double.parseDouble(advField.getText());
        } catch (NumberFormatException e) {
            showError("ADV must be a number");
            return;
        }

        boolean isCash = cashCheck.isSelected();
        String currency = jpyRadio.isSelected() ? "JPY" : "USD";

        Map<String, Double> fundQuantities = new LinkedHashMap<>();
        for (String fn : fundNames) {
            if (fundChecks.get(fn).isSelected()) {
                int qty = fundQtyInputs.get(fn).getValue();
                if (qty <= 0) {
                    showError("Quantity for " + fn + " must be positive");
                    return;
                }
                fundQuantities.put(fn, (double) qty);
            }
        }

        if (fundQuantities.isEmpty()) {
            showError("Select at least one fund with a quantity");
            return;
        }

        try {
            api.addPosition(symbol, name, price, isCash, adv, currency, 0, fundQuantities);
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
