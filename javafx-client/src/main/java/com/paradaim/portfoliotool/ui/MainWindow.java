package com.paradaim.portfoliotool.ui;

import com.paradaim.portfoliotool.model.*;
import com.paradaim.portfoliotool.service.ApiClient;
import com.paradaim.portfoliotool.ui.dialog.AddPositionDialog;
import com.paradaim.portfoliotool.ui.dialog.TargetPriceDialog;
import com.paradaim.portfoliotool.ui.dialog.TradeDialog;
import javafx.application.Platform;
import javafx.beans.property.SimpleStringProperty;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.geometry.Insets;
import javafx.geometry.Orientation;
import javafx.geometry.Pos;
import javafx.scene.Parent;
import javafx.scene.chart.LineChart;
import javafx.scene.chart.NumberAxis;
import javafx.scene.chart.XYChart;
import javafx.scene.control.*;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.scene.layout.*;
import javafx.stage.FileChooser;
import javafx.stage.Stage;

import java.io.File;
import java.io.IOException;
import java.text.NumberFormat;
import java.util.*;
import java.util.concurrent.CompletableFuture;

/**
 * Main application window for the JavaFX Portfolio.Tool client.
 */
public class MainWindow {

    private final ApiClient api;
    private final Stage stage;
    private final BorderPane root;

    // Data
    private final ObservableList<PositionRow> portfolioData = FXCollections.observableArrayList();
    private final ObservableList<ExecutionData> tradesData = FXCollections.observableArrayList();
    private final ObservableList<FilingData> filingsData = FXCollections.observableArrayList();
    private List<String> fundNames = new ArrayList<>();
    private List<PositionData> positions = new ArrayList<>();

    // UI components
    private TableView<PositionRow> portfolioTable;
    private TableView<ExecutionData> tradesTable;
    private TableView<FilingData> filingsTable;
    private Label statusLabel;
    private Label connectionLabel;
    private Label summaryLabel;
    private SplitPane mainSplit;
    private VBox filingsPanel;
    private boolean filingsVisible = false;
    private Button cashPathBtn;
    private VBox cashPathPanel;
    private boolean cashPathVisible = false;

    public MainWindow(ApiClient api, Stage stage) {
        this.api = api;
        this.stage = stage;
        this.root = new BorderPane();
        buildUI();
    }

    public Parent getRoot() {
        return root;
    }

    // =========================================================================
    //  UI Construction
    // =========================================================================

    private void buildUI() {
        root.setTop(buildMenuBar());
        root.setCenter(buildMainContent());
        root.setBottom(buildStatusBar());
    }

    private MenuBar buildMenuBar() {
        MenuBar menuBar = new MenuBar();

        Menu fileMenu = new Menu("File");
        MenuItem importPortfolio = new MenuItem("Import Portfolio...");
        importPortfolio.setOnAction(e -> importPortfolio());
        MenuItem importFilings = new MenuItem("Import Filings...");
        importFilings.setOnAction(e -> importFilings());
        MenuItem exportTrades = new MenuItem("Export Proposed Trades");
        exportTrades.setOnAction(e -> showInfo("Export", "Use the Python backend to export trades to Excel."));
        MenuItem exit = new MenuItem("Exit");
        exit.setOnAction(e -> Platform.exit());
        fileMenu.getItems().addAll(importPortfolio, importFilings, new SeparatorMenuItem(), exportTrades, new SeparatorMenuItem(), exit);

        Menu actionsMenu = new Menu("Actions");
        MenuItem refreshPrices = new MenuItem("Refresh Prices (YFinance)");
        refreshPrices.setOnAction(e -> refreshPrices());
        MenuItem addPosition = new MenuItem("Add Position...");
        addPosition.setOnAction(e -> addPosition());
        actionsMenu.getItems().addAll(refreshPrices, addPosition);

        Menu viewMenu = new Menu("View");
        MenuItem toggleFilings = new MenuItem("Toggle Filings Panel");
        toggleFilings.setOnAction(e -> toggleFilings());
        MenuItem toggleCashPathItem = new MenuItem("Toggle Cash Path");
        toggleCashPathItem.setOnAction(e -> toggleCashPath());
        MenuItem refreshView = new MenuItem("Refresh Data");
        refreshView.setOnAction(e -> refreshAll());
        viewMenu.getItems().addAll(toggleFilings, toggleCashPathItem, refreshView);

        menuBar.getMenus().addAll(fileMenu, actionsMenu, viewMenu);
        return menuBar;
    }

    private SplitPane buildMainContent() {
        mainSplit = new SplitPane();
        mainSplit.setOrientation(Orientation.HORIZONTAL);

        // Left: Portfolio panel
        VBox portfolioPanel = buildPortfolioPanel();

        // Middle: Filings panel (hidden by default)
        filingsPanel = buildFilingsPanel();
        filingsPanel.setVisible(false);
        filingsPanel.setManaged(false);

        // Right: Proposed trades panel
        VBox tradesPanel = buildTradesPanel();

        mainSplit.getItems().addAll(portfolioPanel, tradesPanel);
        mainSplit.setDividerPositions(0.7);

        return mainSplit;
    }

    // -- Portfolio panel -------------------------------------------------------

    private VBox buildPortfolioPanel() {
        VBox panel = new VBox(8);
        panel.setPadding(new Insets(8));

        // Toolbar
        HBox toolbar = new HBox(8);
        toolbar.setAlignment(Pos.CENTER_LEFT);

        Button importBtn = new Button("Import Portfolio");
        importBtn.getStyleClass().add("primary");
        importBtn.setOnAction(e -> importPortfolio());

        Button tradeBtn = new Button("Create Trade");
        tradeBtn.setOnAction(e -> createTrade());

        Button addBtn = new Button("Add Position");
        addBtn.setOnAction(e -> addPosition());

        Button removeBtn = new Button("Remove Position");
        removeBtn.setOnAction(e -> removePosition());

        Button refreshBtn = new Button("Refresh Prices");
        refreshBtn.setOnAction(e -> refreshPrices());

        Button filingsBtn = new Button("Toggle Filings");
        filingsBtn.setOnAction(e -> toggleFilings());

        Region spacer = new Region();
        HBox.setHgrow(spacer, Priority.ALWAYS);

        summaryLabel = new Label("No portfolio loaded");
        summaryLabel.setStyle("-fx-font-style: italic;");

        toolbar.getChildren().addAll(importBtn, tradeBtn, addBtn, removeBtn, refreshBtn, filingsBtn, spacer, summaryLabel);

        // Portfolio table
        portfolioTable = new TableView<>(portfolioData);
        portfolioTable.setPlaceholder(new Label("Import a portfolio to begin"));
        portfolioTable.getSelectionModel().setSelectionMode(SelectionMode.SINGLE);
        VBox.setVgrow(portfolioTable, Priority.ALWAYS);

        buildPortfolioColumns();

        panel.getChildren().addAll(toolbar, portfolioTable);
        return panel;
    }

    private void buildPortfolioColumns() {
        portfolioTable.getColumns().clear();

        TableColumn<PositionRow, String> symbolCol = new TableColumn<>("Symbol");
        symbolCol.setCellValueFactory(new PropertyValueFactory<>("symbol"));
        symbolCol.setPrefWidth(80);

        TableColumn<PositionRow, String> nameCol = new TableColumn<>("Name");
        nameCol.setCellValueFactory(new PropertyValueFactory<>("name"));
        nameCol.setPrefWidth(180);

        TableColumn<PositionRow, String> priceCol = new TableColumn<>("Price (JPY)");
        priceCol.setCellValueFactory(new PropertyValueFactory<>("priceDisplay"));
        priceCol.setPrefWidth(100);
        priceCol.setStyle("-fx-alignment: CENTER-RIGHT;");

        TableColumn<PositionRow, String> pctCol = new TableColumn<>("% of Company");
        pctCol.setCellValueFactory(new PropertyValueFactory<>("pctOfCompanyDisplay"));
        pctCol.setPrefWidth(100);
        pctCol.setStyle("-fx-alignment: CENTER-RIGHT;");

        portfolioTable.getColumns().addAll(symbolCol, nameCol, priceCol, pctCol);
    }

    private void rebuildFundColumns() {
        // Remove old fund columns (keep first 4 fixed columns)
        while (portfolioTable.getColumns().size() > 4) {
            portfolioTable.getColumns().remove(4);
        }

        for (int i = 0; i < fundNames.size(); i++) {
            String fundName = fundNames.get(i);
            int fundIdx = i;

            TableColumn<PositionRow, String> fundGroup = new TableColumn<>(fundName);

            TableColumn<PositionRow, String> currCol = new TableColumn<>("Curr.");
            currCol.setCellValueFactory(cd -> {
                PositionRow row = cd.getValue();
                return new SimpleStringProperty(row.getFundRelWeight(fundIdx));
            });
            currCol.setPrefWidth(60);
            currCol.setStyle("-fx-alignment: CENTER-RIGHT;");

            TableColumn<PositionRow, String> newCol = new TableColumn<>("New");
            newCol.setCellValueFactory(cd -> {
                PositionRow row = cd.getValue();
                return new SimpleStringProperty(row.getFundNewRelWeight(fundIdx));
            });
            newCol.setPrefWidth(60);
            newCol.setStyle("-fx-alignment: CENTER-RIGHT;");

            // Color "New" column cells based on trade direction
            newCol.setCellFactory(col -> new TableCell<>() {
                @Override
                protected void updateItem(String item, boolean empty) {
                    super.updateItem(item, empty);
                    if (empty || item == null) {
                        setText(null);
                        setStyle("-fx-alignment: CENTER-RIGHT;");
                        return;
                    }
                    setText(item);
                    try {
                        double curr = Double.parseDouble(
                            getTableView().getItems().get(getIndex())
                                .getFundRelWeight(fundIdx).replace("x", ""));
                        double newVal = Double.parseDouble(item.replace("x", ""));
                        if (newVal > curr + 0.01) {
                            setStyle("-fx-alignment: CENTER-RIGHT; -fx-text-fill: #008800; -fx-font-weight: bold;");
                        } else if (newVal < curr - 0.01) {
                            setStyle("-fx-alignment: CENTER-RIGHT; -fx-text-fill: #cc0000; -fx-font-weight: bold;");
                        } else {
                            setStyle("-fx-alignment: CENTER-RIGHT;");
                        }
                    } catch (Exception e) {
                        setStyle("-fx-alignment: CENTER-RIGHT;");
                    }
                }
            });

            fundGroup.getColumns().addAll(currCol, newCol);
            portfolioTable.getColumns().add(fundGroup);
        }
    }

    // -- Filings panel --------------------------------------------------------

    private VBox buildFilingsPanel() {
        VBox panel = new VBox(8);
        panel.setPadding(new Insets(8));
        panel.setPrefWidth(350);

        Label header = new Label("Filings");
        header.setStyle("-fx-font-weight: bold; -fx-font-size: 14px;");

        filingsTable = new TableView<>(filingsData);
        filingsTable.setPlaceholder(new Label("No filings loaded"));
        VBox.setVgrow(filingsTable, Priority.ALWAYS);

        TableColumn<FilingData, String> symCol = new TableColumn<>("Symbol");
        symCol.setCellValueFactory(new PropertyValueFactory<>("symbol"));
        symCol.setPrefWidth(70);

        TableColumn<FilingData, String> nameCol = new TableColumn<>("Name");
        nameCol.setCellValueFactory(new PropertyValueFactory<>("name"));
        nameCol.setPrefWidth(100);

        TableColumn<FilingData, String> dateCol = new TableColumn<>("Date");
        dateCol.setCellValueFactory(new PropertyValueFactory<>("date"));
        dateCol.setPrefWidth(80);

        TableColumn<FilingData, String> lastCol = new TableColumn<>("Last Filing %");
        lastCol.setCellValueFactory(cd -> {
            Double lf = cd.getValue().getLastFiling();
            return new SimpleStringProperty(lf != null ? String.format("%.2f%%", lf * 100) : "-");
        });
        lastCol.setPrefWidth(80);

        TableColumn<FilingData, String> upCol = new TableColumn<>("To Upward");
        upCol.setCellValueFactory(cd -> {
            Double val = cd.getValue().getPctToUpward();
            return new SimpleStringProperty(val != null ? String.format("%.2f%%", val * 100) : "-");
        });
        upCol.setPrefWidth(75);

        TableColumn<FilingData, String> downCol = new TableColumn<>("To Downward");
        downCol.setCellValueFactory(cd -> {
            Double val = cd.getValue().getPctToDownward();
            return new SimpleStringProperty(val != null ? String.format("%.2f%%", val * 100) : "-");
        });
        downCol.setPrefWidth(80);

        filingsTable.getColumns().addAll(symCol, nameCol, dateCol, lastCol, upCol, downCol);

        panel.getChildren().addAll(header, filingsTable);
        return panel;
    }

    // -- Proposed Trades panel ------------------------------------------------

    private VBox buildTradesPanel() {
        VBox panel = new VBox(8);
        panel.setPadding(new Insets(8));

        Label header = new Label("Proposed Trades");
        header.setStyle("-fx-font-weight: bold; -fx-font-size: 14px;");

        // Toolbar
        HBox toolbar = new HBox(8);
        Button editPriceBtn = new Button("Edit Target Price");
        editPriceBtn.setOnAction(e -> editTargetPrice());
        Button deleteBtn = new Button("Delete Trade");
        deleteBtn.getStyleClass().add("danger");
        deleteBtn.setOnAction(e -> deleteTrade());
        cashPathBtn = new Button("Show Cash Path");
        cashPathBtn.setOnAction(e -> toggleCashPath());
        toolbar.getChildren().addAll(editPriceBtn, deleteBtn, cashPathBtn);

        tradesTable = new TableView<>(tradesData);
        tradesTable.setPlaceholder(new Label("No proposed trades"));
        VBox.setVgrow(tradesTable, Priority.ALWAYS);

        TableColumn<ExecutionData, String> typeCol = new TableColumn<>("Type");
        typeCol.setCellValueFactory(new PropertyValueFactory<>("tradeType"));
        typeCol.setPrefWidth(50);
        typeCol.setCellFactory(col -> new TableCell<>() {
            @Override
            protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                if (empty || item == null) {
                    setText(null);
                    setStyle("");
                    return;
                }
                setText(item);
                if ("Buy".equals(item)) {
                    setStyle("-fx-text-fill: #008800; -fx-font-weight: bold;");
                } else {
                    setStyle("-fx-text-fill: #cc0000; -fx-font-weight: bold;");
                }
            }
        });

        TableColumn<ExecutionData, String> fundCol = new TableColumn<>("Fund");
        fundCol.setCellValueFactory(new PropertyValueFactory<>("fund"));
        fundCol.setPrefWidth(70);

        TableColumn<ExecutionData, String> symCol = new TableColumn<>("Symbol");
        symCol.setCellValueFactory(new PropertyValueFactory<>("symbol"));
        symCol.setPrefWidth(70);

        TableColumn<ExecutionData, String> qtyCol = new TableColumn<>("Quantity");
        qtyCol.setCellValueFactory(cd ->
            new SimpleStringProperty(formatNumber(cd.getValue().getTradeQuantity())));
        qtyCol.setPrefWidth(80);
        qtyCol.setStyle("-fx-alignment: CENTER-RIGHT;");

        TableColumn<ExecutionData, String> usdCol = new TableColumn<>("USD Value");
        usdCol.setCellValueFactory(cd ->
            new SimpleStringProperty(formatNumber(cd.getValue().getTradeValueUsd()) + " USD"));
        usdCol.setPrefWidth(100);
        usdCol.setStyle("-fx-alignment: CENTER-RIGHT;");

        TableColumn<ExecutionData, String> daysCol = new TableColumn<>("Days");
        daysCol.setCellValueFactory(cd ->
            new SimpleStringProperty(String.format("%.1f", cd.getValue().getTradingDays())));
        daysCol.setPrefWidth(50);
        daysCol.setStyle("-fx-alignment: CENTER-RIGHT;");

        TableColumn<ExecutionData, String> tgtCol = new TableColumn<>("Target PX");
        tgtCol.setCellValueFactory(cd -> {
            Double tp = cd.getValue().getTargetPrice();
            return new SimpleStringProperty(tp != null ? formatNumber(tp) : "-");
        });
        tgtCol.setPrefWidth(80);
        tgtCol.setStyle("-fx-alignment: CENTER-RIGHT;");

        TableColumn<ExecutionData, String> pctCol = new TableColumn<>("% to Curr");
        pctCol.setCellValueFactory(cd -> {
            Double p = cd.getValue().getPctToCurr();
            return new SimpleStringProperty(p != null ? String.format("%.1f%%", p) : "-");
        });
        pctCol.setPrefWidth(70);
        pctCol.setStyle("-fx-alignment: CENTER-RIGHT;");

        tradesTable.getColumns().addAll(typeCol, fundCol, symCol, qtyCol, usdCol, daysCol, tgtCol, pctCol);

        // Net total label
        Label netLabel = new Label("Net Total: -");
        netLabel.setStyle("-fx-font-weight: bold;");
        netLabel.setId("netTotalLabel");

        // Cash path chart panel (hidden by default)
        cashPathPanel = new VBox(4);
        cashPathPanel.setVisible(false);
        cashPathPanel.setManaged(false);

        panel.getChildren().addAll(header, toolbar, tradesTable, netLabel, cashPathPanel);
        return panel;
    }

    // -- Status bar -----------------------------------------------------------

    private HBox buildStatusBar() {
        HBox bar = new HBox(16);
        bar.getStyleClass().add("status-bar");
        bar.setPadding(new Insets(4, 8, 4, 8));
        bar.setAlignment(Pos.CENTER_LEFT);

        connectionLabel = new Label("Disconnected");
        connectionLabel.getStyleClass().add("disconnected");

        statusLabel = new Label("Ready");

        Region spacer = new Region();
        HBox.setHgrow(spacer, Priority.ALWAYS);

        Label versionLabel = new Label("Portfolio.Tool v2.0 - JavaFX Client");

        bar.getChildren().addAll(connectionLabel, new Separator(Orientation.VERTICAL), statusLabel, spacer, versionLabel);
        return bar;
    }

    // =========================================================================
    //  Actions
    // =========================================================================

    public void checkConnection() {
        runAsync(() -> api.isConnected(), connected -> {
            if (connected) {
                connectionLabel.setText("Connected");
                connectionLabel.getStyleClass().remove("disconnected");
                connectionLabel.getStyleClass().add("connected");
                refreshAll();
            } else {
                connectionLabel.setText("Disconnected - Start API server on port 8000");
                showError("Connection Failed",
                    "Could not connect to the API server.\n\n" +
                    "Start the server with:\n  cd PMT && python api_server.py\n\n" +
                    "Then use View > Refresh Data to reconnect.");
            }
        });
    }

    private void refreshAll() {
        setStatus("Refreshing data...");
        runAsync(() -> {
            List<PositionData> pos = api.getPositions();
            PortfolioSummary summary = api.getPortfolioSummary();
            List<ExecutionData> trades = api.getTrades();
            List<FilingData> filings = api.getFilings();
            return new Object[]{pos, summary, trades, filings};
        }, result -> {
            Object[] data = (Object[]) result;
            @SuppressWarnings("unchecked")
            List<PositionData> pos = (List<PositionData>) data[0];
            PortfolioSummary summary = (PortfolioSummary) data[1];
            @SuppressWarnings("unchecked")
            List<ExecutionData> trades = (List<ExecutionData>) data[2];
            @SuppressWarnings("unchecked")
            List<FilingData> filings = (List<FilingData>) data[3];

            positions = pos;
            fundNames = summary.getFundNames() != null ? summary.getFundNames() : new ArrayList<>();

            updatePortfolioTable(pos);
            rebuildFundColumns();
            updateTradesTable(trades);
            updateFilingsTable(filings);
            updateSummary(summary);
            setStatus("Data refreshed");
            refreshCashPath();
        });
    }

    private void importPortfolio() {
        FileChooser fc = new FileChooser();
        fc.setTitle("Import Portfolio");
        fc.getExtensionFilters().add(new FileChooser.ExtensionFilter("Excel Files", "*.xlsx", "*.xls"));
        File file = fc.showOpenDialog(stage);
        if (file == null) return;

        setStatus("Importing portfolio...");
        runAsync(() -> api.importPortfolio(file), msg -> {
            setStatus(msg);
            refreshAll();
        });
    }

    private void importFilings() {
        FileChooser fc = new FileChooser();
        fc.setTitle("Import Filings");
        fc.getExtensionFilters().add(new FileChooser.ExtensionFilter("Excel Files", "*.xlsx", "*.xls"));
        File file = fc.showOpenDialog(stage);
        if (file == null) return;

        setStatus("Importing filings...");
        runAsync(() -> api.importFilings(file), msg -> {
            setStatus(msg);
            refreshAll();
        });
    }

    private void createTrade() {
        PositionRow selected = portfolioTable.getSelectionModel().getSelectedItem();
        if (selected == null) {
            showError("No Selection", "Select a position in the portfolio table first.");
            return;
        }
        if (fundNames.isEmpty()) {
            showError("No Funds", "Import a portfolio with fund data first.");
            return;
        }

        // Find the full position data
        PositionData posData = positions.stream()
                .filter(p -> p.getSymbol().equals(selected.getSymbol()))
                .findFirst().orElse(null);
        if (posData == null) return;

        TradeDialog dialog = new TradeDialog(stage, api, posData, fundNames);
        dialog.showAndWait();
        if (dialog.isSubmitted()) {
            refreshAll();
        }
    }

    private void addPosition() {
        if (fundNames.isEmpty()) {
            showError("No Funds", "Import a portfolio first to establish fund names.");
            return;
        }

        AddPositionDialog dialog = new AddPositionDialog(stage, api, fundNames);
        dialog.showAndWait();
        if (dialog.isSubmitted()) {
            refreshAll();
        }
    }

    private void removePosition() {
        PositionRow selected = portfolioTable.getSelectionModel().getSelectedItem();
        if (selected == null) {
            showError("No Selection", "Select a position to remove.");
            return;
        }

        Alert confirm = new Alert(Alert.AlertType.CONFIRMATION,
                "Remove position " + selected.getSymbol() + "?",
                ButtonType.YES, ButtonType.NO);
        confirm.setHeaderText("Confirm Removal");
        confirm.showAndWait().ifPresent(btn -> {
            if (btn == ButtonType.YES) {
                runAsync(() -> api.removePosition(selected.getSymbol()), msg -> {
                    setStatus(msg);
                    refreshAll();
                });
            }
        });
    }

    private void refreshPrices() {
        setStatus("Refreshing prices from YFinance...");
        runAsync(() -> api.refreshPrices(), msg -> {
            setStatus(msg);
            refreshAll();
        });
    }

    private void editTargetPrice() {
        ExecutionData selected = tradesTable.getSelectionModel().getSelectedItem();
        if (selected == null) {
            showError("No Selection", "Select a trade to edit.");
            return;
        }

        // Find position price
        double currentPrice = positions.stream()
                .filter(p -> p.getSymbol().equals(selected.getSymbol()))
                .findFirst()
                .map(PositionData::getPrice)
                .orElse(0.0);

        TargetPriceDialog dialog = new TargetPriceDialog(stage, selected.getSymbol(),
                currentPrice, selected.getTargetPrice());
        dialog.showAndWait();
        if (dialog.getTargetPrice() != null) {
            runAsync(() -> api.updateTargetPrice(selected.getKey(), dialog.getTargetPrice()), msg -> {
                setStatus(msg);
                refreshAll();
            });
        }
    }

    private void deleteTrade() {
        ExecutionData selected = tradesTable.getSelectionModel().getSelectedItem();
        if (selected == null) {
            showError("No Selection", "Select a trade to delete.");
            return;
        }

        Alert confirm = new Alert(Alert.AlertType.CONFIRMATION,
                "Delete trade " + selected.getKey() + "?",
                ButtonType.YES, ButtonType.NO);
        confirm.setHeaderText("Confirm Deletion");
        confirm.showAndWait().ifPresent(btn -> {
            if (btn == ButtonType.YES) {
                runAsync(() -> api.deleteTrade(selected.getKey()), msg -> {
                    setStatus(msg);
                    refreshAll();
                });
            }
        });
    }

    private void toggleFilings() {
        filingsVisible = !filingsVisible;
        if (filingsVisible) {
            filingsPanel.setVisible(true);
            filingsPanel.setManaged(true);
            if (!mainSplit.getItems().contains(filingsPanel)) {
                mainSplit.getItems().add(1, filingsPanel);
                mainSplit.setDividerPositions(0.5, 0.75);
            }
        } else {
            mainSplit.getItems().remove(filingsPanel);
            filingsPanel.setVisible(false);
            filingsPanel.setManaged(false);
        }
    }

    private void toggleCashPath() {
        cashPathVisible = !cashPathVisible;
        if (cashPathVisible) {
            cashPathBtn.setText("Hide Cash Path");
            cashPathPanel.setVisible(true);
            cashPathPanel.setManaged(true);
            refreshCashPath();
        } else {
            cashPathBtn.setText("Show Cash Path");
            cashPathPanel.setVisible(false);
            cashPathPanel.setManaged(false);
        }
    }

    private void refreshCashPath() {
        if (!cashPathVisible || fundNames.isEmpty()) return;
        setStatus("Loading cash path...");

        runAsync(() -> {
            List<CashPathResponse> responses = new ArrayList<>();
            for (String fund : fundNames) {
                responses.add(api.getCashPath(fund));
            }
            return responses;
        }, responses -> {
            cashPathPanel.getChildren().clear();
            for (CashPathResponse resp : responses) {
                cashPathPanel.getChildren().add(buildCashPathChart(resp));
            }
            setStatus("Cash path loaded");
        });
    }

    @SuppressWarnings("unchecked")
    private VBox buildCashPathChart(CashPathResponse resp) {
        int maxDay = resp.getCashPath().stream().mapToInt(CashPathPoint::getDay).max().orElse(5);

        // --- Primary chart: aggregate cash position line ---
        NumberAxis xAxis = new NumberAxis();
        xAxis.setLabel("Trading Day");
        xAxis.setAutoRanging(false);
        xAxis.setLowerBound(0);
        xAxis.setUpperBound(maxDay);
        xAxis.setTickUnit(1);

        NumberAxis yAxis = new NumberAxis();
        yAxis.setLabel("Cash Position (mm USD)");

        LineChart<Number, Number> chart = new LineChart<>(xAxis, yAxis);
        chart.setTitle(String.format("%s — Cash: %.1fmm | Min: %.1fmm | End: %.1fmm",
                resp.getFund(), resp.getCurrentCashMm(), resp.getMinCashMm(), resp.getEndingCashMm()));
        chart.setPrefHeight(220);
        chart.setCreateSymbols(true);
        chart.setAnimated(false);
        chart.setLegendVisible(true);

        // Aggregate cash position line (cumulative, reflects all buys and sells)
        XYChart.Series<Number, Number> cashSeries = new XYChart.Series<>();
        cashSeries.setName("Cash Position (mm USD)");
        for (CashPathPoint pt : resp.getCashPath()) {
            cashSeries.getData().add(new XYChart.Data<>(pt.getDay(), pt.getCashMm()));
        }
        chart.getData().add(cashSeries);

        // Per-security cumulative contribution lines
        // These show how each trade adds to/subtracts from cash over its trading days
        for (CashPathSeries s : resp.getSeries()) {
            XYChart.Series<Number, Number> tradeSeries = new XYChart.Series<>();
            String direction = "Sell".equals(s.getTradeType()) ? "+" : "-";
            tradeSeries.setName(s.getSymbol() + " (" + s.getTradeType() + " " + direction + ")");

            // Convert daily flows to cumulative contribution
            double cumulative = 0.0;
            tradeSeries.getData().add(new XYChart.Data<>(0, 0.0));
            for (int i = 0; i < s.getDays().size(); i++) {
                cumulative += s.getValues().get(i);
                tradeSeries.getData().add(new XYChart.Data<>(s.getDays().get(i), cumulative));
            }
            chart.getData().add(tradeSeries);
        }

        // --- Trade breakdown summary below the chart ---
        VBox tradeInfo = new VBox(2);
        tradeInfo.setPadding(new Insets(2, 8, 4, 8));
        for (CashPathSeries s : resp.getSeries()) {
            double totalImpact = s.getValues().stream().mapToDouble(Double::doubleValue).sum();
            int numDays = s.getDays().stream().mapToInt(Integer::intValue).max().orElse(0);
            String arrow = totalImpact >= 0 ? "\u2191" : "\u2193";  // up/down arrow
            String color = totalImpact >= 0 ? "#008800" : "#cc0000";
            Label lbl = new Label(String.format("  %s %s: %.2fmm over %d days (%s)",
                    arrow, s.getSymbol(), totalImpact, numDays, s.getTradeType()));
            lbl.setStyle(String.format("-fx-font-size: 11px; -fx-text-fill: %s;", color));
            tradeInfo.getChildren().add(lbl);
        }

        VBox wrapper = new VBox(4, chart, tradeInfo);
        wrapper.setPadding(new Insets(4, 0, 4, 0));
        return wrapper;
    }

    // =========================================================================
    //  Data update
    // =========================================================================

    private void updatePortfolioTable(List<PositionData> positions) {
        portfolioData.clear();
        for (PositionData pos : positions) {
            portfolioData.add(new PositionRow(pos, fundNames));
        }
    }

    private void updateTradesTable(List<ExecutionData> trades) {
        tradesData.setAll(trades);

        // Update net total
        double net = trades.stream().mapToDouble(ExecutionData::getTradeValueSigned).sum();
        Label netLabel = (Label) root.lookup("#netTotalLabel");
        if (netLabel != null) {
            netLabel.setText(String.format("Net Total: %s USD", formatNumber(net)));
            if (net > 0) {
                netLabel.setStyle("-fx-font-weight: bold; -fx-text-fill: #008800;");
            } else if (net < 0) {
                netLabel.setStyle("-fx-font-weight: bold; -fx-text-fill: #cc0000;");
            } else {
                netLabel.setStyle("-fx-font-weight: bold;");
            }
        }
    }

    private void updateFilingsTable(List<FilingData> filings) {
        filingsData.setAll(filings);
    }

    private void updateSummary(PortfolioSummary summary) {
        if (summary.getNumPositions() == 0) {
            summaryLabel.setText("No portfolio loaded");
        } else {
            summaryLabel.setText(String.format(
                "%d positions | %s funds | Rate: %.2f",
                summary.getNumPositions(),
                summary.getFundNames() != null ? String.join(", ", summary.getFundNames()) : "-",
                summary.getUsdJpyRate()
            ));
        }
    }

    // =========================================================================
    //  Helpers
    // =========================================================================

    private void setStatus(String text) {
        Platform.runLater(() -> statusLabel.setText(text));
    }

    private void showError(String title, String message) {
        Platform.runLater(() -> {
            Alert alert = new Alert(Alert.AlertType.ERROR, message, ButtonType.OK);
            alert.setHeaderText(title);
            alert.showAndWait();
        });
    }

    private void showInfo(String title, String message) {
        Platform.runLater(() -> {
            Alert alert = new Alert(Alert.AlertType.INFORMATION, message, ButtonType.OK);
            alert.setHeaderText(title);
            alert.showAndWait();
        });
    }

    private static String formatNumber(double value) {
        return NumberFormat.getIntegerInstance().format((long) value);
    }

    /**
     * Run a task asynchronously and handle the result on the JavaFX thread.
     */
    private <T> void runAsync(ThrowingSupplier<T> task, java.util.function.Consumer<T> onSuccess) {
        CompletableFuture.supplyAsync(() -> {
            try {
                return task.get();
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }).thenAccept(result -> Platform.runLater(() -> onSuccess.accept(result)))
          .exceptionally(ex -> {
              Platform.runLater(() -> {
                  setStatus("Error: " + ex.getCause().getMessage());
                  showError("Error", ex.getCause().getMessage());
              });
              return null;
          });
    }

    @FunctionalInterface
    interface ThrowingSupplier<T> {
        T get() throws Exception;
    }

    // =========================================================================
    //  Portfolio row model for TableView
    // =========================================================================

    public static class PositionRow {
        private final PositionData data;
        private final List<String> fundNames;

        public PositionRow(PositionData data, List<String> fundNames) {
            this.data = data;
            this.fundNames = fundNames;
        }

        public String getSymbol() { return data.getSymbol(); }
        public String getName() { return data.getName(); }

        public String getPriceDisplay() {
            return NumberFormat.getIntegerInstance().format((long) data.getPrice());
        }

        public String getPctOfCompanyDisplay() {
            return String.format("%.2f%%", data.getTotalPctOfCompany() * 100);
        }

        public String getFundRelWeight(int fundIdx) {
            if (fundIdx >= fundNames.size()) return "";
            String fundName = fundNames.get(fundIdx);
            if (data.getFunds() == null) return "";
            FundPositionData fp = data.getFunds().get(fundName);
            if (fp == null || data.isCash()) return "";
            return String.format("%.2fx", fp.getRelWeight());
        }

        public String getFundNewRelWeight(int fundIdx) {
            if (fundIdx >= fundNames.size()) return "";
            String fundName = fundNames.get(fundIdx);
            if (data.getFunds() == null) return "";
            FundPositionData fp = data.getFunds().get(fundName);
            if (fp == null || data.isCash()) return "";
            return String.format("%.2fx", fp.getNewRelWeight());
        }
    }
}
