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
import javafx.scene.Node;
import javafx.scene.Parent;
import javafx.scene.chart.LineChart;
import javafx.scene.chart.NumberAxis;
import javafx.scene.chart.XYChart;
import javafx.scene.control.*;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.scene.input.KeyCode;
import javafx.scene.input.KeyCodeCombination;
import javafx.scene.input.KeyCombination;
import javafx.scene.layout.*;
import javafx.stage.FileChooser;
import javafx.stage.Stage;

import java.io.File;
import java.io.IOException;
import java.text.NumberFormat;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;
import java.util.stream.Collectors;

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
    private VBox tradesPanel;
    // (tradeChartSplit removed – cash path is now in bottomSplit)

    // Default sort flag (set before refreshAll after import)
    private boolean applyDefaultSort = false;

    // Font scaling
    private int fontSize = 12;
    private static final int MIN_FONT_SIZE = 8;
    private static final int MAX_FONT_SIZE = 24;

    public MainWindow(ApiClient api, Stage stage) {
        this.api = api;
        this.stage = stage;
        this.root = new BorderPane();
        buildUI();
        setupKeyboardShortcuts();
    }

    public Parent getRoot() {
        return root;
    }

    // =========================================================================
    //  UI Construction
    // =========================================================================

    // Sub/Red tab components
    private TableView<ScheduleItem> scheduleTable;
    private Label scheduleInfoLabel;
    private ScheduleResponse lastSchedule;
    private boolean showShares = false;  // false = show $ amount (default), true = show shares
    private ToggleButton displayToggle;

    private static final String CUMUL_USD_MARKER = "__CUMUL_USD__";
    private static final String CUMUL_PCT_MARKER = "__CUMUL_PCT__";

    // Correlation tab components
    private TableView<CorrelationRow> corrTable;
    private Label corrInfoLabel;
    private Label corrAvgLabel;
    private ComboBox<String> corrLookbackCombo;
    private ComboBox<String> corrPeriodicityCombo;
    private final List<String> corrSymbols = new ArrayList<>();
    private final List<String> corrNames = new ArrayList<>();
    private CorrelationResponse lastCorrelation;

    private void buildUI() {
        root.setTop(buildMenuBar());

        TabPane tabPane = new TabPane();
        tabPane.setTabClosingPolicy(TabPane.TabClosingPolicy.UNAVAILABLE);

        Tab portfolioTab = new Tab("Current Portfolio", buildMainContent());
        Tab subRedTab = new Tab("Subscription/Redemption", buildSubRedTab());
        Tab corrTab = new Tab("Correlation Matrix", buildCorrelationTab());

        tabPane.getTabs().addAll(portfolioTab, subRedTab, corrTab);
        root.setCenter(tabPane);
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
        MenuItem refreshPrices = new MenuItem("Refresh Prices (J-Quants)");
        refreshPrices.setOnAction(e -> refreshPrices());
        MenuItem refreshMetrics = new MenuItem("Refresh Metrics (J-Quants)");
        refreshMetrics.setOnAction(e -> refreshMetrics());
        MenuItem addPosition = new MenuItem("Add Position...");
        addPosition.setOnAction(e -> addPosition());
        actionsMenu.getItems().addAll(refreshPrices, refreshMetrics, addPosition);

        Menu viewMenu = new Menu("View");
        MenuItem toggleFilings = new MenuItem("Toggle Filings Panel");
        toggleFilings.setOnAction(e -> toggleFilings());
        MenuItem toggleCashPathItem = new MenuItem("Toggle Cash Path");
        toggleCashPathItem.setOnAction(e -> toggleCashPath());
        MenuItem refreshView = new MenuItem("Refresh Data");
        refreshView.setOnAction(e -> refreshAll());

        SeparatorMenuItem viewSep = new SeparatorMenuItem();
        MenuItem increaseFontItem = new MenuItem("Increase Font Size");
        increaseFontItem.setAccelerator(new KeyCodeCombination(KeyCode.EQUALS, KeyCombination.CONTROL_DOWN));
        increaseFontItem.setOnAction(e -> changeFontSize(1));
        MenuItem decreaseFontItem = new MenuItem("Decrease Font Size");
        decreaseFontItem.setAccelerator(new KeyCodeCombination(KeyCode.MINUS, KeyCombination.CONTROL_DOWN));
        decreaseFontItem.setOnAction(e -> changeFontSize(-1));
        MenuItem resetFontItem = new MenuItem("Reset Font Size");
        resetFontItem.setAccelerator(new KeyCodeCombination(KeyCode.DIGIT0, KeyCombination.CONTROL_DOWN));
        resetFontItem.setOnAction(e -> { fontSize = 12; applyFontSize(); });

        viewMenu.getItems().addAll(toggleFilings, toggleCashPathItem, refreshView,
                viewSep, increaseFontItem, decreaseFontItem, resetFontItem);

        menuBar.getMenus().addAll(fileMenu, actionsMenu, viewMenu);
        return menuBar;
    }

    private SplitPane bottomSplit;

    private SplitPane buildMainContent() {
        mainSplit = new SplitPane();
        mainSplit.setOrientation(Orientation.VERTICAL);

        // Top: Portfolio panel (positions with metrics)
        VBox portfolioPanel = buildPortfolioPanel();

        // Middle: Filings panel (hidden by default)
        filingsPanel = buildFilingsPanel();
        filingsPanel.setVisible(false);
        filingsPanel.setManaged(false);

        // Bottom: horizontal split with trades (left) and cash path (right)
        tradesPanel = buildTradesPanel();
        cashPathPanel = new VBox(4);
        cashPathPanel.setPadding(new Insets(8));

        bottomSplit = new SplitPane();
        bottomSplit.setOrientation(Orientation.HORIZONTAL);
        bottomSplit.getItems().add(tradesPanel);
        bottomSplit.setDividerPositions(0.5);

        mainSplit.getItems().addAll(portfolioPanel, bottomSplit);
        mainSplit.setDividerPositions(0.55);

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
        importBtn.setOnAction(e -> importPortfolio());

        Button tradeBtn = new Button("Create Trade");
        tradeBtn.setOnAction(e -> createTrade());

        Button addBtn = new Button("Add Position");
        addBtn.setOnAction(e -> addPosition());

        Button removeBtn = new Button("Remove Position");
        removeBtn.setOnAction(e -> removePosition());

        Button refreshBtn = new Button("Refresh Prices");
        refreshBtn.setOnAction(e -> refreshPrices());

        Button refreshMetricsBtn = new Button("Refresh Metrics");
        refreshMetricsBtn.setOnAction(e -> refreshMetrics());

        Button filingsBtn = new Button("Toggle Filings");
        filingsBtn.setOnAction(e -> toggleFilings());

        Button importFilingsBtn = new Button("Import Filings");
        importFilingsBtn.setOnAction(e -> importFilings());

        Region spacer = new Region();
        HBox.setHgrow(spacer, Priority.ALWAYS);

        summaryLabel = new Label("No portfolio loaded");
        summaryLabel.setStyle("-fx-font-style: italic;");

        toolbar.getChildren().addAll(importBtn, tradeBtn, addBtn, removeBtn, refreshBtn, refreshMetricsBtn, filingsBtn, importFilingsBtn, spacer, summaryLabel);

        // Portfolio table
        portfolioTable = new TableView<>(portfolioData);
        portfolioTable.setPlaceholder(new Label("Import a portfolio to begin"));
        portfolioTable.getSelectionModel().setSelectionMode(SelectionMode.SINGLE);
        portfolioTable.setOnMouseClicked(event -> {
            if (event.getClickCount() == 2 && portfolioTable.getSelectionModel().getSelectedItem() != null) {
                createTrade();
            }
        });
        VBox.setVgrow(portfolioTable, Priority.ALWAYS);

        // Custom sort policy: cash rows always pinned to bottom
        portfolioTable.setSortPolicy(table -> {
            FXCollections.sort(table.getItems(), (a, b) -> {
                boolean aCash = a.getData().isCash();
                boolean bCash = b.getData().isCash();
                if (aCash && !bCash) return 1;
                if (!aCash && bCash) return -1;
                if (aCash && bCash) return 0;
                // Apply the table's current sort order for non-cash rows
                Comparator<PositionRow> tableComparator = (Comparator<PositionRow>) table.getComparator();
                if (tableComparator != null) {
                    return tableComparator.compare(a, b);
                }
                return 0;
            });
            return true;
        });

        buildPortfolioColumns();

        panel.getChildren().addAll(toolbar, portfolioTable);
        return panel;
    }

    private static final int NUM_FIXED_COLUMNS = 5; // Symbol, Name, Price, % of Company, Age
    private static final int NUM_METRIC_COLUMNS = 26; // 16 metrics + 10 returns (incl. inception)

    private void buildPortfolioColumns() {
        portfolioTable.getColumns().clear();

        TableColumn<PositionRow, String> symbolCol = new TableColumn<>("Symbol");
        symbolCol.setCellValueFactory(new PropertyValueFactory<>("symbol"));
        symbolCol.setPrefWidth(80);
        symbolCol.setCellFactory(col -> new TableCell<>() {
            @Override
            protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                if (empty || item == null) {
                    setText(null);
                    setStyle("");
                    return;
                }
                setText(item);
                PositionRow row = getTableView().getItems().get(getIndex());
                if (row.getData().isNew()) {
                    setStyle("-fx-text-fill: #1a53ff; -fx-font-weight: bold;");
                } else {
                    setStyle("");
                }
            }
        });

        TableColumn<PositionRow, String> nameCol = new TableColumn<>("Name");
        nameCol.setCellValueFactory(new PropertyValueFactory<>("name"));
        nameCol.setPrefWidth(180);
        nameCol.setCellFactory(col -> new TableCell<>() {
            @Override
            protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                if (empty || item == null) {
                    setText(null);
                    setStyle("");
                    return;
                }
                setText(item);
                PositionRow row = getTableView().getItems().get(getIndex());
                if (row.getData().isNew()) {
                    setStyle("-fx-text-fill: #1a53ff; -fx-font-weight: bold;");
                } else {
                    setStyle("");
                }
            }
        });

        TableColumn<PositionRow, String> priceCol = new TableColumn<>("Price (JPY)");
        priceCol.setCellValueFactory(new PropertyValueFactory<>("priceDisplay"));
        priceCol.setPrefWidth(100);
        priceCol.setStyle("-fx-alignment: CENTER-RIGHT;");
        priceCol.setComparator(NUMERIC_STRING_COMPARATOR);

        TableColumn<PositionRow, String> pctCol = new TableColumn<>("% of Company");
        pctCol.setCellValueFactory(new PropertyValueFactory<>("pctOfCompanyDisplay"));
        pctCol.setPrefWidth(100);
        pctCol.setStyle("-fx-alignment: CENTER-RIGHT;");
        pctCol.setComparator(NUMERIC_STRING_COMPARATOR);

        TableColumn<PositionRow, String> ageCol = new TableColumn<>("Age (yr)");
        ageCol.setCellValueFactory(new PropertyValueFactory<>("ageDisplay"));
        ageCol.setPrefWidth(60);
        ageCol.setStyle("-fx-alignment: CENTER-RIGHT;");
        ageCol.setComparator(NUMERIC_STRING_COMPARATOR);

        portfolioTable.getColumns().addAll(symbolCol, nameCol, priceCol, pctCol, ageCol);

        // Metrics columns: (header, property, width, extractor, higherIsBetter)
        // Lower is better: PBR, PE*, PEG*, beta, payout
        // Higher is better: ROE*, plowback, divYield, OPM, growth rates
        addMetricCol("PBR",      "pbr",          55, PositionData::getPbr,        false);
        addMetricCol("PE LTM",   "peLtm",        60, PositionData::getPeLtm,      false);
        addMetricCol("PE NTM",   "peNtm",        60, PositionData::getPeNtm,      false);
        addMetricCol("PE 24M",   "pe24m",        60, PositionData::getPe24m,      false);
        addMetricCol("PEGc",     "pegC",         55, PositionData::getPegC,       false);
        addMetricCol("PEG n",    "pegN",         55, PositionData::getPegN,       false);
        addMetricCol("ROE(l)",   "roeL",         60, PositionData::getRoeL,       true);
        addMetricCol("ROE NTM",  "roeNtm",       65, PositionData::getRoeNtm,     true);
        addMetricCol("b(plow)",  "plowback",     55, PositionData::getPlowback,   true);
        addMetricCol("b(vol)",   "beta",         55, PositionData::getBeta,       false);
        addMetricCol("DivYld",   "divYield",     60, PositionData::getDivYield,   true);
        addMetricCol("Payout",   "payoutRatio",  60, PositionData::getPayoutRatio,false);
        addMetricCol("OPM",      "opm",          55, PositionData::getOpm,        true);
        addMetricCol("2Y Sales", "salesCagr2y",  60, PositionData::getSalesCagr2y,true);
        addMetricCol("2Y Op",    "opCagr2y",     55, PositionData::getOpCagr2y,   true);
        addMetricCol("2Y EPS",   "epsCagr2y",    55, PositionData::getEpsCagr2y,  true);

        // Return columns
        addReturnCol("Incep", "retIncep", 55, PositionData::getRetIncep);
        addReturnCol("1D",   "ret1d",   50, PositionData::getRet1d);
        addReturnCol("1W",   "ret1w",   50, PositionData::getRet1w);
        addReturnCol("1M",   "ret1m",   50, PositionData::getRet1m);
        addReturnCol("3M",   "ret3m",   50, PositionData::getRet3m);
        addReturnCol("6M",   "ret6m",   50, PositionData::getRet6m);
        addReturnCol("YTD",  "retYtd",  50, PositionData::getRetYtd);
        addReturnCol("1Y",   "ret1y",   55, PositionData::getRet1y);
        addReturnCol("3Y",   "ret3y",   55, PositionData::getRet3y);
        addReturnCol("5Y",   "ret5y",   55, PositionData::getRet5y);
    }

    private void addMetricCol(String header, String property, int width,
                              Function<PositionData, Double> extractor, boolean higherIsBetter) {
        TableColumn<PositionRow, String> col = new TableColumn<>(header);
        col.setCellValueFactory(new PropertyValueFactory<>(property));
        col.setPrefWidth(width);
        col.setStyle("-fx-alignment: CENTER-RIGHT;");
        col.setComparator(NUMERIC_STRING_COMPARATOR);

        col.setCellFactory(column -> new TableCell<>() {
            @Override
            protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                if (empty || item == null || item.isEmpty()) {
                    setText(null);
                    setStyle("-fx-alignment: CENTER-RIGHT;");
                    return;
                }
                setText(item);

                // Get raw value for this row
                PositionRow row = getTableView().getItems().get(getIndex());
                Double rawValue = extractor.apply(row.getData());
                if (rawValue == null) {
                    setStyle("-fx-alignment: CENTER-RIGHT;");
                    return;
                }

                // Collect all non-null values in this column
                List<Double> values = getTableView().getItems().stream()
                        .map(r -> extractor.apply(r.getData()))
                        .filter(Objects::nonNull)
                        .sorted()
                        .collect(Collectors.toList());

                if (values.size() <= 1) {
                    setStyle("-fx-alignment: CENTER-RIGHT;");
                    return;
                }

                // Compute percentile rank (0 = lowest, 1 = highest)
                int idx = Collections.binarySearch(values, rawValue);
                if (idx < 0) idx = -(idx + 1);
                // Handle duplicate values: find first occurrence
                while (idx > 0 && values.get(idx - 1).equals(rawValue)) idx--;
                double rank = (double) idx / (values.size() - 1);

                // Convert rank to attractiveness (0 = worst, 1 = best)
                double attractiveness = higherIsBetter ? rank : (1.0 - rank);

                // Interpolate color: 0 = pink (#E6B8B7), 0.5 = white, 1 = green (#C4D79B)
                int r, g, b;
                if (attractiveness >= 0.5) {
                    double t = (attractiveness - 0.5) * 2.0;
                    r = (int) (255 - t * (255 - 196));
                    g = (int) (255 - t * (255 - 215));
                    b = (int) (255 - t * (255 - 155));
                } else {
                    double t = attractiveness * 2.0;
                    r = (int) (230 + t * (255 - 230));
                    g = (int) (184 + t * (255 - 184));
                    b = (int) (183 + t * (255 - 183));
                }

                String bgColor = String.format("#%02X%02X%02X", r, g, b);
                setStyle("-fx-alignment: CENTER-RIGHT; -fx-background-color: " + bgColor + ";");
            }
        });

        portfolioTable.getColumns().add(col);
    }

    private void addReturnCol(String header, String property, int width,
                              Function<PositionData, Double> extractor) {
        TableColumn<PositionRow, String> col = new TableColumn<>(header);
        col.setCellValueFactory(new PropertyValueFactory<>(property));
        col.setPrefWidth(width);
        col.setStyle("-fx-alignment: CENTER-RIGHT;");
        col.setComparator(NUMERIC_STRING_COMPARATOR);

        col.setCellFactory(column -> new TableCell<>() {
            @Override
            protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                if (empty || item == null || item.isEmpty()) {
                    setText(null);
                    setStyle("-fx-alignment: CENTER-RIGHT;");
                    return;
                }
                setText(item);
                try {
                    PositionRow row = getTableView().getItems().get(getIndex());
                    Double rawValue = extractor.apply(row.getData());
                    if (rawValue == null) {
                        setStyle("-fx-alignment: CENTER-RIGHT;");
                    } else if (rawValue > 0) {
                        setStyle("-fx-alignment: CENTER-RIGHT; -fx-text-fill: #008800;");
                    } else if (rawValue < 0) {
                        setStyle("-fx-alignment: CENTER-RIGHT; -fx-text-fill: #cc0000;");
                    } else {
                        setStyle("-fx-alignment: CENTER-RIGHT;");
                    }
                } catch (Exception e) {
                    setStyle("-fx-alignment: CENTER-RIGHT;");
                }
            }
        });

        portfolioTable.getColumns().add(col);
    }

    private void rebuildFundColumns() {
        // Remove old fund columns (they sit between fixed columns and metric columns)
        // Total columns = fixed + fund + metric; fund columns start at NUM_FIXED_COLUMNS
        int totalExpected = NUM_FIXED_COLUMNS + NUM_METRIC_COLUMNS;
        while (portfolioTable.getColumns().size() > totalExpected) {
            portfolioTable.getColumns().remove(NUM_FIXED_COLUMNS);
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
            currCol.setComparator(NUMERIC_STRING_COMPARATOR);

            TableColumn<PositionRow, String> newCol = new TableColumn<>("New");
            newCol.setCellValueFactory(cd -> {
                PositionRow row = cd.getValue();
                return new SimpleStringProperty(row.getFundNewRelWeight(fundIdx));
            });
            newCol.setPrefWidth(60);
            newCol.setStyle("-fx-alignment: CENTER-RIGHT;");
            newCol.setComparator(NUMERIC_STRING_COMPARATOR);

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
            // Insert fund columns right after fixed columns (before metrics)
            portfolioTable.getColumns().add(NUM_FIXED_COLUMNS + i, fundGroup);
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
        lastCol.setComparator(NUMERIC_STRING_COMPARATOR);

        TableColumn<FilingData, String> upCol = new TableColumn<>("To Upward");
        upCol.setCellValueFactory(cd -> {
            Double val = cd.getValue().getPctToUpward();
            return new SimpleStringProperty(val != null ? String.format("%.2f%%", val * 100) : "-");
        });
        upCol.setPrefWidth(75);
        upCol.setComparator(NUMERIC_STRING_COMPARATOR);

        TableColumn<FilingData, String> downCol = new TableColumn<>("To Downward");
        downCol.setCellValueFactory(cd -> {
            Double val = cd.getValue().getPctToDownward();
            return new SimpleStringProperty(val != null ? String.format("%.2f%%", val * 100) : "-");
        });
        downCol.setPrefWidth(80);
        downCol.setComparator(NUMERIC_STRING_COMPARATOR);

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
        deleteBtn.setOnAction(e -> deleteTrade());
        cashPathBtn = new Button("Show Cash Path");
        cashPathBtn.setOnAction(e -> toggleCashPath());
        toolbar.getChildren().addAll(editPriceBtn, deleteBtn, cashPathBtn);

        tradesTable = new TableView<>(tradesData);
        tradesTable.setPlaceholder(new Label("No proposed trades"));
        tradesTable.setMinHeight(80);
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

        TableColumn<ExecutionData, String> nameCol = new TableColumn<>("Name");
        nameCol.setCellValueFactory(new PropertyValueFactory<>("name"));
        nameCol.setPrefWidth(120);

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
        qtyCol.setComparator(NUMERIC_STRING_COMPARATOR);

        TableColumn<ExecutionData, String> usdCol = new TableColumn<>("USD Value");
        usdCol.setCellValueFactory(cd ->
            new SimpleStringProperty(formatNumber(cd.getValue().getTradeValueUsd()) + " USD"));
        usdCol.setPrefWidth(100);
        usdCol.setStyle("-fx-alignment: CENTER-RIGHT;");
        usdCol.setComparator(NUMERIC_STRING_COMPARATOR);

        TableColumn<ExecutionData, String> daysCol = new TableColumn<>("Days");
        daysCol.setCellValueFactory(cd ->
            new SimpleStringProperty(String.format("%.1f", cd.getValue().getTradingDays())));
        daysCol.setPrefWidth(50);
        daysCol.setStyle("-fx-alignment: CENTER-RIGHT;");
        daysCol.setComparator(NUMERIC_STRING_COMPARATOR);

        TableColumn<ExecutionData, String> tgtCol = new TableColumn<>("Target PX");
        tgtCol.setCellValueFactory(cd -> {
            Double tp = cd.getValue().getTargetPrice();
            return new SimpleStringProperty(tp != null ? formatNumber(tp) : "-");
        });
        tgtCol.setPrefWidth(80);
        tgtCol.setStyle("-fx-alignment: CENTER-RIGHT;");
        tgtCol.setComparator(NUMERIC_STRING_COMPARATOR);

        TableColumn<ExecutionData, String> pctCol = new TableColumn<>("% to Curr");
        pctCol.setCellValueFactory(cd -> {
            Double p = cd.getValue().getPctToCurr();
            return new SimpleStringProperty(p != null ? String.format("%.1f%%", p) : "-");
        });
        pctCol.setPrefWidth(70);
        pctCol.setStyle("-fx-alignment: CENTER-RIGHT;");
        pctCol.setComparator(NUMERIC_STRING_COMPARATOR);

        tradesTable.getColumns().addAll(typeCol, nameCol, fundCol, symCol, qtyCol, usdCol, daysCol, tgtCol, pctCol);

        // Net total label
        Label netLabel = new Label("Net Total: -");
        netLabel.setStyle("-fx-font-weight: bold;");
        netLabel.setId("netTotalLabel");

        panel.getChildren().addAll(header, toolbar, tradesTable, netLabel);
        return panel;
    }

    // -- Subscription/Redemption tab ------------------------------------------

    private VBox buildSubRedTab() {
        VBox tab = new VBox(8);
        tab.setPadding(new Insets(8));

        // Toolbar
        HBox toolbar = new HBox(8);
        toolbar.setAlignment(Pos.CENTER_LEFT);

        Button importBtn = new Button("Import Portfolio");
        importBtn.setOnAction(e -> importPortfolioForSubRed());
        Button subBtn = new Button("Create Subscription");
        subBtn.setOnAction(e -> openSubRedDialog("subscription"));
        Button redBtn = new Button("Create Redemption");
        redBtn.setOnAction(e -> openSubRedDialog("redemption"));

        displayToggle = new ToggleButton("Show Shares");
        displayToggle.setSelected(false);
        displayToggle.setOnAction(e -> {
            showShares = displayToggle.isSelected();
            displayToggle.setText(showShares ? "Show Amount" : "Show Shares");
            if (lastSchedule != null) {
                buildScheduleColumns(lastSchedule.getTotalWeeks());
                List<ScheduleItem> tableItems = new ArrayList<>();
                tableItems.addAll(buildSummaryRows(lastSchedule));
                tableItems.addAll(lastSchedule.getItems());
                scheduleTable.getItems().setAll(tableItems);
            }
        });

        toolbar.getChildren().addAll(importBtn, subBtn, redBtn, displayToggle);

        // Info label
        scheduleInfoLabel = new Label("Import a portfolio and click Create Subscription or Create Redemption to generate a schedule.");
        scheduleInfoLabel.setStyle("-fx-font-size: 13px;");

        // Schedule table
        scheduleTable = new TableView<>();
        scheduleTable.setPlaceholder(new Label("Import a portfolio to begin"));
        VBox.setVgrow(scheduleTable, Priority.ALWAYS);

        tab.getChildren().addAll(toolbar, scheduleInfoLabel, scheduleTable);
        return tab;
    }

    private void importPortfolioForSubRed() {
        importPortfolio();
    }

    private void refreshSubRedPositions() {
        runAsync(() -> api.getPositions(), positionsList -> {
            buildPositionColumns();
            ObservableList<ScheduleItem> items = FXCollections.observableArrayList();
            for (PositionData p : positionsList) {
                if (p.isCash()) continue;
                if (p.getTotalQuantity() <= 0) continue;
                ScheduleItem si = new ScheduleItem();
                si.setSymbol(p.getSymbol());
                si.setName(p.getName());
                si.setTotalQuantity(p.getTotalQuantity());
                si.setTradingDays(0);
                si.setWeeks(new ArrayList<>());
                items.add(si);
            }
            scheduleTable.getItems().setAll(items);
            lastSchedule = null;
            scheduleInfoLabel.setText("Portfolio loaded \u2014 " + items.size()
                    + " positions. Click Create Subscription or Create Redemption to generate a schedule.");
        });
    }

    @SuppressWarnings("unchecked")
    private void buildPositionColumns() {
        scheduleTable.getColumns().clear();

        TableColumn<ScheduleItem, String> symCol = new TableColumn<>("Symbol");
        symCol.setCellValueFactory(new PropertyValueFactory<>("symbol"));
        symCol.setPrefWidth(80);

        TableColumn<ScheduleItem, String> nameCol = new TableColumn<>("Name");
        nameCol.setCellValueFactory(new PropertyValueFactory<>("name"));
        nameCol.setPrefWidth(150);

        TableColumn<ScheduleItem, String> qtyCol = new TableColumn<>("Quantity");
        qtyCol.setCellValueFactory(cd -> {
            double qty = cd.getValue().getTotalQuantity();
            return new SimpleStringProperty(formatNumber(qty));
        });
        qtyCol.setPrefWidth(100);
        qtyCol.setStyle("-fx-alignment: CENTER-RIGHT;");

        scheduleTable.getColumns().addAll(symCol, nameCol, qtyCol);
    }

    private boolean isSummaryRow(ScheduleItem item) {
        String sym = item.getSymbol();
        return CUMUL_USD_MARKER.equals(sym) || CUMUL_PCT_MARKER.equals(sym);
    }

    @SuppressWarnings("unchecked")
    private void buildScheduleColumns(int totalWeeks) {
        scheduleTable.getColumns().clear();

        String boldStyle = "-fx-font-weight: bold; -fx-background-color: #f0f0f0;";

        TableColumn<ScheduleItem, String> symCol = new TableColumn<>("Symbol");
        symCol.setCellValueFactory(cd -> {
            if (isSummaryRow(cd.getValue())) return new SimpleStringProperty("");
            return new SimpleStringProperty(cd.getValue().getSymbol());
        });
        symCol.setCellFactory(col -> new TableCell<>() {
            @Override protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                setText(empty ? null : item);
                setStyle(getTableRow() != null && getTableRow().getItem() != null
                        && isSummaryRow(getTableRow().getItem())
                        ? boldStyle : "");
            }
        });
        symCol.setPrefWidth(80);

        TableColumn<ScheduleItem, String> nameCol = new TableColumn<>("Name");
        nameCol.setCellValueFactory(cd -> {
            ScheduleItem si = cd.getValue();
            if (CUMUL_USD_MARKER.equals(si.getSymbol())) return new SimpleStringProperty("Cumulative $");
            if (CUMUL_PCT_MARKER.equals(si.getSymbol())) return new SimpleStringProperty("Cumulative %");
            return new SimpleStringProperty(si.getName());
        });
        nameCol.setCellFactory(col -> new TableCell<>() {
            @Override protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                setText(empty ? null : item);
                setStyle(getTableRow() != null && getTableRow().getItem() != null
                        && isSummaryRow(getTableRow().getItem())
                        ? boldStyle : "");
            }
        });
        nameCol.setPrefWidth(150);

        TableColumn<ScheduleItem, String> qtyCol = new TableColumn<>("Quantity");
        qtyCol.setCellValueFactory(cd -> {
            if (isSummaryRow(cd.getValue())) return new SimpleStringProperty("");
            double qty = cd.getValue().getTotalQuantity();
            return new SimpleStringProperty(formatNumber(qty));
        });
        qtyCol.setCellFactory(col -> new TableCell<>() {
            @Override protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                setText(empty ? null : item);
                setStyle(getTableRow() != null && getTableRow().getItem() != null
                        && isSummaryRow(getTableRow().getItem())
                        ? boldStyle + " -fx-alignment: CENTER-RIGHT;" : "-fx-alignment: CENTER-RIGHT;");
            }
        });
        qtyCol.setPrefWidth(100);

        TableColumn<ScheduleItem, String> daysCol = new TableColumn<>("Trading Days");
        daysCol.setCellValueFactory(cd -> {
            if (isSummaryRow(cd.getValue())) return new SimpleStringProperty("");
            double td = cd.getValue().getTradingDays();
            return new SimpleStringProperty(td > 0 ? String.format("%.1f", td) : "\u2014");
        });
        daysCol.setCellFactory(col -> new TableCell<>() {
            @Override protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                setText(empty ? null : item);
                setStyle(getTableRow() != null && getTableRow().getItem() != null
                        && isSummaryRow(getTableRow().getItem())
                        ? boldStyle + " -fx-alignment: CENTER-RIGHT;" : "-fx-alignment: CENTER-RIGHT;");
            }
        });
        daysCol.setPrefWidth(90);

        scheduleTable.getColumns().addAll(symCol, nameCol, qtyCol, daysCol);

        double usdJpyRate = lastSchedule != null ? lastSchedule.getUsdJpyRate() : 1.0;

        for (int w = 0; w < totalWeeks; w++) {
            final int weekIdx = w;
            TableColumn<ScheduleItem, String> weekCol = new TableColumn<>("Week " + (w + 1));
            weekCol.setCellValueFactory(cd -> {
                ScheduleItem si = cd.getValue();
                List<Double> weeks = si.getWeeks();
                if (weeks == null || weekIdx >= weeks.size()) return new SimpleStringProperty("");
                double val = weeks.get(weekIdx);

                if (CUMUL_USD_MARKER.equals(si.getSymbol())) {
                    return new SimpleStringProperty(String.format("$%,.1fmm", val / 1e6));
                }
                if (CUMUL_PCT_MARKER.equals(si.getSymbol())) {
                    return new SimpleStringProperty(String.format("%,.1f%%", val));
                }

                if (showShares) {
                    double priceJpy = si.getPriceJpy();
                    if (priceJpy > 0) {
                        double shares = val * usdJpyRate / priceJpy;
                        return new SimpleStringProperty(formatNumber(shares));
                    }
                    return new SimpleStringProperty("\u2014");
                }
                return new SimpleStringProperty(String.format("$%.2fmm", val / 1e6));
            });
            weekCol.setCellFactory(col -> new TableCell<>() {
                @Override protected void updateItem(String item, boolean empty) {
                    super.updateItem(item, empty);
                    setText(empty ? null : item);
                    setStyle(getTableRow() != null && getTableRow().getItem() != null
                            && isSummaryRow(getTableRow().getItem())
                            ? boldStyle + " -fx-alignment: CENTER-RIGHT;" : "-fx-alignment: CENTER-RIGHT;");
                }
            });
            weekCol.setPrefWidth(100);
            scheduleTable.getColumns().add(weekCol);
        }
    }

    /**
     * Build two sentinel ScheduleItem rows for cumulative $ and cumulative %.
     * The weeks list holds pre-computed running totals (USD for $ row, percentage for % row).
     */
    private List<ScheduleItem> buildSummaryRows(ScheduleResponse response) {
        int totalWeeks = response.getTotalWeeks();
        double totalAmount = response.getAmountUsd();

        List<Double> cumulUsd = new ArrayList<>();
        List<Double> cumulPct = new ArrayList<>();

        double runningSum = 0.0;
        for (int w = 0; w < totalWeeks; w++) {
            double weekSum = 0.0;
            for (ScheduleItem item : response.getItems()) {
                List<Double> weeks = item.getWeeks();
                if (weeks != null && w < weeks.size()) {
                    weekSum += weeks.get(w);
                }
            }
            runningSum += weekSum;
            cumulUsd.add(runningSum);
            cumulPct.add(totalAmount > 0 ? (runningSum / totalAmount) * 100.0 : 0.0);
        }

        ScheduleItem usdRow = new ScheduleItem();
        usdRow.setSymbol(CUMUL_USD_MARKER);
        usdRow.setName("Cumulative $");
        usdRow.setWeeks(cumulUsd);

        ScheduleItem pctRow = new ScheduleItem();
        pctRow.setSymbol(CUMUL_PCT_MARKER);
        pctRow.setName("Cumulative %");
        pctRow.setWeeks(cumulPct);

        return List.of(usdRow, pctRow);
    }

    // -- Correlation Matrix tab -----------------------------------------------

    private VBox buildCorrelationTab() {
        VBox tab = new VBox(8);
        tab.setPadding(new Insets(8));

        HBox toolbar = new HBox(8);
        toolbar.setAlignment(Pos.CENTER_LEFT);

        Button importBtn = new Button("Import Portfolio");
        importBtn.setOnAction(e -> importPortfolioForCorrelation());

        Button runBtn = new Button("Run Correlation");
        runBtn.setOnAction(e -> runCorrelation());

        corrLookbackCombo = new ComboBox<>();
        corrLookbackCombo.getItems().addAll("6m", "1y", "2y", "3y", "5y", "10y");
        corrLookbackCombo.setValue("3y");

        corrPeriodicityCombo = new ComboBox<>();
        corrPeriodicityCombo.getItems().addAll("Daily", "Weekly", "Monthly", "Quarterly", "Annually");
        corrPeriodicityCombo.setValue("Weekly");

        Button addCandidateBtn = new Button("Add Candidate");
        addCandidateBtn.setOnAction(e -> showAddCandidateDialog());

        toolbar.getChildren().addAll(importBtn, runBtn,
                new Label("Lookback:"), corrLookbackCombo,
                new Label("Periodicity:"), corrPeriodicityCombo,
                addCandidateBtn);

        corrInfoLabel = new Label("Import a portfolio, then click Run Correlation.");
        corrInfoLabel.setStyle("-fx-font-size: 13px;");

        corrAvgLabel = new Label();
        corrAvgLabel.setStyle("-fx-font-size: 13px; -fx-font-weight: bold;");
        corrAvgLabel.setVisible(false);
        corrAvgLabel.setManaged(false);

        corrTable = new TableView<>();
        corrTable.setPlaceholder(new Label("Import a portfolio to begin"));
        VBox.setVgrow(corrTable, Priority.ALWAYS);

        tab.getChildren().addAll(toolbar, corrInfoLabel, corrAvgLabel, corrTable);
        return tab;
    }

    private void importPortfolioForCorrelation() {
        importPortfolio();
    }

    private void loadCorrelationPositions() {
        runAsync(() -> api.getPositions(), positionsList -> {
            corrSymbols.clear();
            corrNames.clear();
            for (PositionData p : positionsList) {
                if (p.isCash()) continue;
                if (p.getTotalQuantity() <= 0) continue;
                corrSymbols.add(p.getSymbol());
                corrNames.add(p.getName());
            }
            lastCorrelation = null;
            corrAvgLabel.setVisible(false);
            corrAvgLabel.setManaged(false);
            buildCorrPositionColumns();
            corrInfoLabel.setText("Portfolio loaded \u2014 " + corrSymbols.size()
                    + " symbols. Click Run Correlation to compute the matrix.");
        });
    }

    @SuppressWarnings("unchecked")
    private void buildCorrPositionColumns() {
        corrTable.getColumns().clear();
        corrTable.getItems().clear();

        TableColumn<CorrelationRow, String> symCol = new TableColumn<>("Symbol");
        symCol.setCellValueFactory(new PropertyValueFactory<>("symbol"));
        symCol.setPrefWidth(80);

        TableColumn<CorrelationRow, String> nameCol = new TableColumn<>("Name");
        nameCol.setCellValueFactory(new PropertyValueFactory<>("name"));
        nameCol.setPrefWidth(150);

        corrTable.getColumns().addAll(symCol, nameCol);

        ObservableList<CorrelationRow> items = FXCollections.observableArrayList();
        for (int i = 0; i < corrSymbols.size(); i++) {
            CorrelationRow row = new CorrelationRow();
            row.setSymbol(corrSymbols.get(i));
            row.setName(corrNames.get(i));
            items.add(row);
        }
        corrTable.getItems().setAll(items);
    }

    private void runCorrelation() {
        if (corrSymbols.size() < 2) {
            showError("Error", "Import a portfolio with at least 2 non-cash positions first.");
            return;
        }
        String lookback = corrLookbackCombo.getValue();
        String periodicity = corrPeriodicityCombo.getValue().toLowerCase();

        setStatus("Computing correlation matrix (" + lookback + " / " + periodicity + ")...");
        corrInfoLabel.setText("Fetching historical data and computing correlations...");

        runAsync(
            () -> api.calculateCorrelation(
                    new ArrayList<>(corrSymbols), new ArrayList<>(corrNames),
                    lookback, periodicity),
            response -> {
                lastCorrelation = response;
                buildCorrMatrixColumns(response);
                corrTable.getItems().setAll(response.getRows());
                corrInfoLabel.setText(String.format(
                        "Correlation Matrix  |  %d symbols  |  Lookback: %s  |  Periodicity: %s",
                        response.getSymbols().size(), lookback,
                        corrPeriodicityCombo.getValue()));

                // Compute and display portfolio-wide average correlation
                double totalCorr = 0;
                int count = 0;
                for (CorrelationRow row : response.getRows()) {
                    if (row.getAvgCorrelation() != null) {
                        totalCorr += row.getAvgCorrelation();
                        count++;
                    }
                }
                if (count > 0) {
                    corrAvgLabel.setText(String.format("Portfolio Average Correlation: %.4f", totalCorr / count));
                    corrAvgLabel.setVisible(true);
                    corrAvgLabel.setManaged(true);
                } else {
                    corrAvgLabel.setVisible(false);
                    corrAvgLabel.setManaged(false);
                }

                setStatus("Correlation matrix computed for " + response.getSymbols().size() + " symbols");
            }
        );
    }

    /**
     * Interpolate a correlation value to a background color.
     * Uses the same green-to-pink scheme as the portfolio tab but inverted:
     * lowest correlation = green (#C4D79B), highest = pink (#E6B8B7), mid = white.
     */
    private String corrColor(double value, double minVal, double maxVal) {
        if (maxVal <= minVal) return "";
        double rank = (value - minVal) / (maxVal - minVal); // 0=lowest, 1=highest
        // For correlation: high = pink (less desirable), low = green (more desirable)
        double attractiveness = 1.0 - rank;
        int r, g, b;
        if (attractiveness >= 0.5) {
            double t = (attractiveness - 0.5) * 2.0;
            r = (int) (255 - t * (255 - 196));
            g = (int) (255 - t * (255 - 215));
            b = (int) (255 - t * (255 - 155));
        } else {
            double t = attractiveness * 2.0;
            r = (int) (230 + t * (255 - 230));
            g = (int) (184 + t * (255 - 184));
            b = (int) (183 + t * (255 - 183));
        }
        return String.format("-fx-background-color: #%02X%02X%02X;", r, g, b);
    }

    @SuppressWarnings("unchecked")
    private void buildCorrMatrixColumns(CorrelationResponse response) {
        corrTable.getColumns().clear();

        String selfStyle = "-fx-alignment: CENTER-RIGHT; -fx-background-color: #f0f0f0;";

        // Collect all correlation values to determine min/max for color scaling
        double allMin = Double.MAX_VALUE, allMax = -Double.MAX_VALUE;
        double avgMin = Double.MAX_VALUE, avgMax = -Double.MAX_VALUE;
        for (CorrelationRow row : response.getRows()) {
            if (row.getAvgCorrelation() != null) {
                avgMin = Math.min(avgMin, row.getAvgCorrelation());
                avgMax = Math.max(avgMax, row.getAvgCorrelation());
            }
            if (row.getCorrelations() != null) {
                for (Double v : row.getCorrelations()) {
                    if (v != null) {
                        allMin = Math.min(allMin, v);
                        allMax = Math.max(allMax, v);
                    }
                }
            }
        }
        final double fAllMin = allMin, fAllMax = allMax;
        final double fAvgMin = avgMin, fAvgMax = avgMax;

        // Avg Correlation column (with conditional formatting)
        TableColumn<CorrelationRow, String> avgCol = new TableColumn<>("Avg Corr");
        avgCol.setCellValueFactory(cd -> {
            Double avg = cd.getValue().getAvgCorrelation();
            return new SimpleStringProperty(avg != null ? String.format("%.2f", avg) : "");
        });
        avgCol.setCellFactory(c -> new TableCell<>() {
            @Override
            protected void updateItem(String item, boolean empty) {
                super.updateItem(item, empty);
                if (empty || item == null || item.isEmpty()) {
                    setText(null);
                    setStyle("-fx-alignment: CENTER-RIGHT;");
                    return;
                }
                setText(item);
                CorrelationRow row = getTableView().getItems().get(getIndex());
                Double avg = row.getAvgCorrelation();
                if (avg != null && fAvgMax > fAvgMin) {
                    setStyle("-fx-alignment: CENTER-RIGHT; -fx-font-weight: bold; "
                            + corrColor(avg, fAvgMin, fAvgMax));
                } else {
                    setStyle("-fx-alignment: CENTER-RIGHT; -fx-font-weight: bold;");
                }
            }
        });
        avgCol.setPrefWidth(80);

        // Symbol column (row header)
        TableColumn<CorrelationRow, String> symCol = new TableColumn<>("Symbol");
        symCol.setCellValueFactory(new PropertyValueFactory<>("symbol"));
        symCol.setPrefWidth(80);

        // Name column
        TableColumn<CorrelationRow, String> nameCol = new TableColumn<>("Name");
        nameCol.setCellValueFactory(new PropertyValueFactory<>("name"));
        nameCol.setPrefWidth(150);

        corrTable.getColumns().addAll(avgCol, symCol, nameCol);

        // One column per symbol
        List<String> symbols = response.getSymbols();
        for (int j = 0; j < symbols.size(); j++) {
            final int colIdx = j;
            TableColumn<CorrelationRow, String> col = new TableColumn<>(symbols.get(j));
            col.setCellValueFactory(cd -> {
                List<Double> corrs = cd.getValue().getCorrelations();
                if (corrs == null || colIdx >= corrs.size()) return new SimpleStringProperty("");
                Double val = corrs.get(colIdx);
                if (val == null) return new SimpleStringProperty("");
                return new SimpleStringProperty(String.format("%.2f", val));
            });
            col.setCellFactory(c -> new TableCell<>() {
                @Override
                protected void updateItem(String item, boolean empty) {
                    super.updateItem(item, empty);
                    if (empty || item == null || item.isEmpty()) {
                        setText(null);
                        // Check if this is a self-correlation cell (diagonal)
                        int rowIdx = getIndex();
                        if (rowIdx >= 0 && rowIdx < symbols.size()
                                && symbols.get(rowIdx).equals(symbols.get(colIdx))) {
                            setStyle(selfStyle);
                        } else {
                            setStyle("-fx-alignment: CENTER-RIGHT;");
                        }
                        return;
                    }
                    setText(item);
                    try {
                        double val = Double.parseDouble(item);
                        setStyle("-fx-alignment: CENTER-RIGHT; " + corrColor(val, fAllMin, fAllMax));
                    } catch (NumberFormatException e) {
                        setStyle("-fx-alignment: CENTER-RIGHT;");
                    }
                }
            });
            col.setPrefWidth(65);
            corrTable.getColumns().add(col);
        }
    }

    private void showAddCandidateDialog() {
        Dialog<String[]> dialog = new Dialog<>();
        dialog.setTitle("Add Candidate");
        dialog.setResizable(true);

        ButtonType addBtn = new ButtonType("Add", ButtonBar.ButtonData.OK_DONE);
        dialog.getDialogPane().getButtonTypes().addAll(addBtn, ButtonType.CANCEL);

        GridPane grid = new GridPane();
        grid.setHgap(10);
        grid.setVgap(10);
        grid.setPadding(new Insets(20));

        TextField tickerField = new TextField();
        tickerField.setPromptText("e.g. 6758");
        TextField nameField = new TextField();
        nameField.setPromptText("e.g. Sony Group Corp");

        grid.add(new Label("Ticker:"), 0, 0);
        grid.add(tickerField, 1, 0);
        grid.add(new Label("Name:"), 0, 1);
        grid.add(nameField, 1, 1);

        dialog.getDialogPane().setContent(grid);
        dialog.getDialogPane().setPrefWidth(350);

        dialog.setResultConverter(btn -> {
            if (btn == addBtn) {
                String ticker = tickerField.getText().trim();
                String name = nameField.getText().trim();
                if (!ticker.isEmpty() && !name.isEmpty()) {
                    return new String[]{ticker, name};
                }
            }
            return null;
        });

        dialog.showAndWait().ifPresent(result -> {
            if (result == null) {
                showError("Error", "Both ticker and name are required.");
                return;
            }
            // Add to the lists and auto-run
            corrSymbols.add(result[0]);
            corrNames.add(result[1]);
            runCorrelation();
        });
    }

    private void openSubRedDialog(String direction) {
        String title = "subscription".equals(direction) ? "Create Subscription" : "Create Redemption";

        Dialog<double[]> dialog = new Dialog<>();
        dialog.setTitle(title);
        dialog.setResizable(true);

        ButtonType calcBtn = new ButtonType("Calculate", ButtonBar.ButtonData.OK_DONE);
        dialog.getDialogPane().getButtonTypes().addAll(calcBtn, ButtonType.CANCEL);

        GridPane grid = new GridPane();
        grid.setHgap(10);
        grid.setVgap(10);
        grid.setPadding(new Insets(20));

        TextField usdField = new TextField();
        usdField.setPromptText("e.g. 500");

        ToggleGroup modeGroup = new ToggleGroup();
        RadioButton maintainRadio = new RadioButton("Maintain Weights");
        maintainRadio.setToggleGroup(modeGroup);
        maintainRadio.setSelected(true);
        RadioButton minimizeRadio = new RadioButton("Minimize Time");
        minimizeRadio.setToggleGroup(modeGroup);

        grid.add(new Label("Amount (USD millions):"), 0, 0);
        grid.add(usdField, 1, 0);
        grid.add(new Label("Execution Mode:"), 0, 1);
        VBox modeBox = new VBox(4, maintainRadio, minimizeRadio);
        grid.add(modeBox, 1, 1);

        dialog.getDialogPane().setContent(grid);
        dialog.getDialogPane().setPrefWidth(400);

        // Convert result
        dialog.setResultConverter(btn -> {
            if (btn == calcBtn) {
                try {
                    double amount = Double.parseDouble(usdField.getText().trim());
                    double modeVal = maintainRadio.isSelected() ? 0 : 1;
                    return new double[]{amount, modeVal};
                } catch (NumberFormatException ex) {
                    return null;
                }
            }
            return null;
        });

        dialog.showAndWait().ifPresent(result -> {
            if (result == null) {
                showError("Error", "Please enter a valid amount.");
                return;
            }
            double amountMm = result[0];
            String mode = result[1] == 0 ? "maintain_weights" : "minimize_time";

            if (amountMm <= 0) {
                showError("Error", "Amount must be positive.");
                return;
            }

            setStatus("Calculating " + direction + " schedule...");
            runAsync(
                () -> api.calculateSchedule(amountMm, mode, direction),
                response -> {
                    lastSchedule = response;
                    String modeLabel = "maintain_weights".equals(response.getMode())
                            ? "Maintain Weights" : "Minimize Time";
                    String dirLabel = response.getDirection().substring(0, 1).toUpperCase()
                            + response.getDirection().substring(1);
                    scheduleInfoLabel.setText(String.format(
                            "%s  |  Amount: $%,.1fmm USD  |  Mode: %s  |  Total Weeks: %d",
                            dirLabel, response.getAmountUsd() / 1e6, modeLabel, response.getTotalWeeks()));

                    buildScheduleColumns(response.getTotalWeeks());
                    List<ScheduleItem> tableItems = new ArrayList<>();
                    tableItems.addAll(buildSummaryRows(response));
                    tableItems.addAll(response.getItems());
                    scheduleTable.getItems().setAll(tableItems);
                    setStatus("Schedule computed: " + response.getItems().size() + " positions, "
                            + response.getTotalWeeks() + " weeks");
                }
            );
        });
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

    /**
     * Refresh all tabs after a portfolio import — Current Portfolio, Sub/Red, and Correlation.
     */
    private void refreshAllTabs() {
        refreshAll();
        refreshSubRedPositions();
        loadCorrelationPositions();
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

            // Save current sort state by column index
            List<Integer> sortColIndices = new ArrayList<>();
            List<TableColumn.SortType> sortTypes = new ArrayList<>();
            for (TableColumn<PositionRow, ?> col : portfolioTable.getSortOrder()) {
                int idx = portfolioTable.getColumns().indexOf(col);
                if (idx < 0) {
                    // Check nested columns (fund group children)
                    for (int g = 0; g < portfolioTable.getColumns().size(); g++) {
                        TableColumn<PositionRow, ?> parent = portfolioTable.getColumns().get(g);
                        int sub = parent.getColumns().indexOf(col);
                        if (sub >= 0) {
                            idx = g * 100 + sub;  // encode as parent*100 + child
                            break;
                        }
                    }
                }
                sortColIndices.add(idx);
                sortTypes.add(col.getSortType());
            }

            positions = pos;
            fundNames = summary.getFundNames() != null ? summary.getFundNames() : new ArrayList<>();

            updatePortfolioTable(pos);
            rebuildFundColumns();
            updateTradesTable(trades);
            updateFilingsTable(filings);
            updateSummary(summary);

            // Restore sort order or apply default sort after import
            if (applyDefaultSort) {
                applyDefaultSort = false;
                // Sort by first fund's "Curr." column descending (fund columns are right after fixed)
                int fundGroupIdx = NUM_FIXED_COLUMNS;
                if (fundGroupIdx < portfolioTable.getColumns().size()) {
                    TableColumn<PositionRow, ?> fundGroup = portfolioTable.getColumns().get(fundGroupIdx);
                    if (!fundGroup.getColumns().isEmpty()) {
                        TableColumn<PositionRow, ?> currCol = fundGroup.getColumns().get(0);
                        currCol.setSortType(TableColumn.SortType.DESCENDING);
                        portfolioTable.getSortOrder().setAll(currCol);
                        portfolioTable.sort();
                    }
                }
            } else if (!sortColIndices.isEmpty()) {
                List<TableColumn<PositionRow, ?>> newSortOrder = new ArrayList<>();
                for (int i = 0; i < sortColIndices.size(); i++) {
                    int idx = sortColIndices.get(i);
                    TableColumn<PositionRow, ?> col = null;
                    if (idx >= 100) {
                        int parentIdx = idx / 100;
                        int childIdx = idx % 100;
                        if (parentIdx < portfolioTable.getColumns().size()) {
                            var parent = portfolioTable.getColumns().get(parentIdx);
                            if (childIdx < parent.getColumns().size()) {
                                col = parent.getColumns().get(childIdx);
                            }
                        }
                    } else if (idx >= 0 && idx < portfolioTable.getColumns().size()) {
                        col = portfolioTable.getColumns().get(idx);
                    }
                    if (col != null) {
                        col.setSortType(sortTypes.get(i));
                        newSortOrder.add(col);
                    }
                }
                portfolioTable.getSortOrder().setAll(newSortOrder);
                portfolioTable.sort();
            }

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
        ProgressDialog progress = showProgressDialog("Importing Portfolio",
                "Reading and processing " + file.getName() + "...");
        progress.show();
        applyDefaultSort = true;
        runAsync(() -> api.importPortfolio(file), msg -> {
            progress.close();
            setStatus(msg);
            refreshAllTabs();
        }, progress);
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

        // Look up filing data for this symbol
        FilingData filingData = null;
        try {
            List<FilingData> filings = api.getFilings();
            for (FilingData fd : filings) {
                if (posData.getSymbol().equals(fd.getSymbol())) {
                    filingData = fd;
                    break;
                }
            }
        } catch (Exception ignored) {
            // Filing data is optional – proceed without it
        }

        TradeDialog dialog = new TradeDialog(stage, api, posData, fundNames, filingData);
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
        setStatus("Refreshing prices from J-Quants...");
        ProgressDialog progress = showProgressDialog("Refreshing Prices",
                "Fetching latest prices and ADV data from J-Quants...");
        progress.show();
        runAsync(() -> api.refreshPrices(), msg -> {
            progress.close();
            setStatus(msg);
            refreshAll();
        }, progress);
    }

    private void refreshMetrics() {
        setStatus("Refreshing metrics from J-Quants...");
        ProgressDialog progress = showProgressDialog("Refreshing Metrics",
                "Fetching fundamental metrics (statements, beta) from J-Quants...\nThis may take a minute.");
        progress.show();
        runAsync(() -> api.refreshMetrics(), msg -> {
            progress.close();
            setStatus(msg);
            refreshAll();
        }, progress);
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
        } else {
            filingsPanel.setVisible(false);
            filingsPanel.setManaged(false);
        }
        rebuildLowerLayout();
    }

    private void toggleCashPath() {
        cashPathVisible = !cashPathVisible;
        if (cashPathVisible) {
            cashPathBtn.setText("Hide Cash Path");
            cashPathPanel.setVisible(true);
            cashPathPanel.setManaged(true);
        } else {
            cashPathBtn.setText("Show Cash Path");
            cashPathPanel.setVisible(false);
            cashPathPanel.setManaged(false);
        }
        rebuildLowerLayout();
        if (cashPathVisible) {
            refreshCashPath();
        }
    }

    /**
     * Rebuilds the lower portion of mainSplit based on filings/cashPath visibility.
     *
     * When cash path is hidden:
     *   mainSplit = portfolioPanel | [filingsPanel] | bottomSplit(tradesPanel)
     *
     * When cash path is visible:
     *   mainSplit = portfolioPanel | bottomSplit( leftColumn(filings+trades) | cashPathChart )
     *   The cash path chart spans the full height of the lower section.
     */
    private void rebuildLowerLayout() {
        // Preserve the portfolio panel (always index 0)
        Node portfolioPanel = mainSplit.getItems().get(0);

        // Remove everything except portfolioPanel
        mainSplit.getItems().clear();
        mainSplit.getItems().add(portfolioPanel);

        bottomSplit.getItems().clear();

        if (cashPathVisible) {
            // Stack filings (if visible) + trades on the left in a resizable SplitPane
            SplitPane leftColumn = new SplitPane();
            leftColumn.setOrientation(Orientation.VERTICAL);
            if (filingsVisible) {
                leftColumn.getItems().addAll(filingsPanel, tradesPanel);
                leftColumn.setDividerPositions(0.25);
            } else {
                leftColumn.getItems().add(tradesPanel);
            }

            ScrollPane chartScroll = new ScrollPane(cashPathPanel);
            chartScroll.setFitToWidth(true);
            chartScroll.setFitToHeight(true);

            bottomSplit.getItems().addAll(leftColumn, chartScroll);
            bottomSplit.setDividerPositions(0.4);

            mainSplit.getItems().add(bottomSplit);
            mainSplit.setDividerPositions(0.35);
        } else {
            // No cash path: filings as separate row in mainSplit, trades in bottomSplit
            bottomSplit.getItems().add(tradesPanel);

            if (filingsVisible) {
                mainSplit.getItems().addAll(filingsPanel, bottomSplit);
                mainSplit.setDividerPositions(0.5, 0.75);
            } else {
                mainSplit.getItems().add(bottomSplit);
                mainSplit.setDividerPositions(0.55);
            }
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
        yAxis.setAutoRanging(true);

        LineChart<Number, Number> chart = new LineChart<>(xAxis, yAxis);
        chart.setTitle(String.format("%s — Cash: %.1fmm | Min: %.1fmm | End: %.1fmm",
                resp.getFund(), resp.getCurrentCashMm(), resp.getMinCashMm(), resp.getEndingCashMm()));
        chart.setMinHeight(100);
        chart.setPrefHeight(Integer.MAX_VALUE);
        chart.setMaxHeight(Double.MAX_VALUE);
        chart.setCreateSymbols(false);
        chart.setAnimated(false);
        chart.setLegendVisible(false);
        VBox.setVgrow(chart, Priority.ALWAYS);

        // Aggregate cash position line (cumulative, reflects all buys and sells)
        XYChart.Series<Number, Number> cashSeries = new XYChart.Series<>();
        cashSeries.setName("Cash Position (mm USD)");
        for (CashPathPoint pt : resp.getCashPath()) {
            cashSeries.getData().add(new XYChart.Data<>(pt.getDay(), pt.getCashMm()));
        }
        chart.getData().add(cashSeries);

        // Style the cash position line: thick, bold blue
        cashSeries.getNode().setStyle("-fx-stroke: #1a53ff; -fx-stroke-width: 2.5px;");

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

            // Style trade lines: thinner, lighter
            tradeSeries.getNode().setStyle("-fx-stroke-width: 1px; -fx-opacity: 0.7;");
        }

        VBox wrapper = new VBox(0, chart);
        wrapper.setPadding(new Insets(0));
        VBox.setVgrow(chart, Priority.ALWAYS);
        VBox.setVgrow(wrapper, Priority.ALWAYS);
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

        // Update net total (cash perspective: sells raise cash, buys spend cash)
        // trade_value_signed is +ve for buys, -ve for sells, so negate for cash impact
        double cashImpact = -trades.stream().mapToDouble(ExecutionData::getTradeValueSigned).sum();
        Label netLabel = (Label) root.lookup("#netTotalLabel");
        if (netLabel != null) {
            netLabel.setText(String.format("Net Total: %s USD", formatNumber(cashImpact)));
            if (cashImpact > 0) {
                // Net sells > buys → raising cash → green
                netLabel.setStyle("-fx-font-weight: bold; -fx-text-fill: #008800;");
            } else if (cashImpact < 0) {
                // Net buys > sells → cash drawdown → red
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
    //  Font scaling
    // =========================================================================

    private void setupKeyboardShortcuts() {
        root.setOnKeyPressed(event -> {
            if (event.isControlDown()) {
                if (event.getCode() == KeyCode.EQUALS || event.getCode() == KeyCode.PLUS) {
                    changeFontSize(1);
                    event.consume();
                } else if (event.getCode() == KeyCode.MINUS) {
                    changeFontSize(-1);
                    event.consume();
                } else if (event.getCode() == KeyCode.DIGIT0) {
                    fontSize = 12;
                    applyFontSize();
                    event.consume();
                }
            }
        });
    }

    private void changeFontSize(int delta) {
        int newSize = Math.max(MIN_FONT_SIZE, Math.min(MAX_FONT_SIZE, fontSize + delta));
        if (newSize != fontSize) {
            fontSize = newSize;
            applyFontSize();
        }
    }

    private void applyFontSize() {
        root.setStyle(String.format("-fx-font-size: %dpx;", fontSize));
    }

    // =========================================================================
    //  Progress dialog
    // =========================================================================

    private ProgressDialog showProgressDialog(String title, String message) {
        return new ProgressDialog(stage, title, message);
    }

    /**
     * Simple modal progress dialog with an indeterminate progress bar.
     */
    private static class ProgressDialog {
        private final javafx.stage.Stage dialog;
        private final Label messageLabel;
        private final ProgressBar progressBar;

        ProgressDialog(Stage owner, String title, String message) {
            dialog = new javafx.stage.Stage();
            dialog.initOwner(owner);
            dialog.initModality(javafx.stage.Modality.APPLICATION_MODAL);
            dialog.setTitle(title);
            dialog.setResizable(false);

            messageLabel = new Label(message);
            messageLabel.setWrapText(true);

            progressBar = new ProgressBar(-1); // indeterminate
            progressBar.setPrefWidth(350);

            VBox content = new VBox(12, messageLabel, progressBar);
            content.setPadding(new Insets(20));
            content.setAlignment(Pos.CENTER);

            dialog.setScene(new javafx.scene.Scene(content));
            dialog.setOnCloseRequest(e -> e.consume()); // prevent manual close
        }

        void show() {
            Platform.runLater(() -> dialog.show());
        }

        void updateMessage(String msg) {
            Platform.runLater(() -> messageLabel.setText(msg));
        }

        void close() {
            Platform.runLater(() -> dialog.close());
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
     * Comparator for table columns that display numeric values as strings.
     * Strips non-numeric chars (commas, %, 'x', 'USD', spaces) and parses as double.
     * Nulls, blanks, and "-" sort to the end.
     */
    private static final Comparator<String> NUMERIC_STRING_COMPARATOR = (a, b) -> {
        Double da = parseNumeric(a);
        Double db = parseNumeric(b);
        if (da == null && db == null) return 0;
        if (da == null) return 1;
        if (db == null) return -1;
        return Double.compare(da, db);
    };

    private static Double parseNumeric(String s) {
        if (s == null || s.isBlank() || "-".equals(s.trim())) return null;
        try {
            String cleaned = s.replaceAll("[^\\d.\\-eE]", "");
            if (cleaned.isEmpty()) return null;
            return Double.parseDouble(cleaned);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /**
     * Run a task asynchronously and handle the result on the JavaFX thread.
     */
    private <T> void runAsync(ThrowingSupplier<T> task, java.util.function.Consumer<T> onSuccess) {
        runAsync(task, onSuccess, null);
    }

    private <T> void runAsync(ThrowingSupplier<T> task, java.util.function.Consumer<T> onSuccess,
                               ProgressDialog progress) {
        CompletableFuture.supplyAsync(() -> {
            try {
                return task.get();
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }).thenAccept(result -> Platform.runLater(() -> onSuccess.accept(result)))
          .exceptionally(ex -> {
              Platform.runLater(() -> {
                  if (progress != null) progress.close();
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

        public PositionData getData() { return data; }

        public String getSymbol() { return data.getSymbol(); }
        public String getName() { return data.getName(); }

        public String getPriceDisplay() {
            return NumberFormat.getIntegerInstance().format((long) data.getPrice());
        }

        public String getPctOfCompanyDisplay() {
            return String.format("%.2f%%", data.getTotalPctOfCompany() * 100);
        }

        public String getAgeDisplay() {
            Double age = data.getAgeYears();
            return age != null ? String.format("%.1f", age) : "";
        }

        public String getFundRelWeight(int fundIdx) {
            if (fundIdx >= fundNames.size()) return "";
            String fundName = fundNames.get(fundIdx);
            if (data.getFunds() == null) return "";
            FundPositionData fp = data.getFunds().get(fundName);
            if (fp == null || data.isCash()) return "";
            // New positions have no "current" weight - leave blank
            if (data.isNew()) return "";
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

        // Metrics accessors
        private String fmtOpt(Double v, String fmt) {
            return v != null ? String.format(fmt, v) : "";
        }
        public String getPbr() { return fmtOpt(data.getPbr(), "%.2f"); }
        public String getPeLtm() { return fmtOpt(data.getPeLtm(), "%.1f"); }
        public String getPeNtm() { return fmtOpt(data.getPeNtm(), "%.1f"); }
        public String getPe24m() { return fmtOpt(data.getPe24m(), "%.1f"); }
        public String getPegC() { return fmtOpt(data.getPegC(), "%.2f"); }
        public String getPegN() { return fmtOpt(data.getPegN(), "%.2f"); }
        public String getRoeL() { return fmtOpt(data.getRoeL(), "%.1f%%"); }
        public String getRoeNtm() { return fmtOpt(data.getRoeNtm(), "%.1f%%"); }
        public String getPlowback() { return fmtOpt(data.getPlowback(), "%.2f"); }
        public String getBeta() { return fmtOpt(data.getBeta(), "%.2f"); }
        public String getDivYield() { return fmtOpt(data.getDivYield(), "%.2f%%"); }
        public String getPayoutRatio() { return fmtOpt(data.getPayoutRatio(), "%.1f%%"); }
        public String getOpm() { return fmtOpt(data.getOpm(), "%.1f%%"); }
        public String getSalesCagr2y() { return fmtOpt(data.getSalesCagr2y(), "%.1f%%"); }
        public String getOpCagr2y() { return fmtOpt(data.getOpCagr2y(), "%.1f%%"); }
        public String getEpsCagr2y() { return fmtOpt(data.getEpsCagr2y(), "%.1f%%"); }

        // Returns accessors
        public String getRetIncep() { return fmtOpt(data.getRetIncep(), "%.1f%%"); }
        public String getRet1d() { return fmtOpt(data.getRet1d(), "%.2f%%"); }
        public String getRet1w() { return fmtOpt(data.getRet1w(), "%.2f%%"); }
        public String getRet1m() { return fmtOpt(data.getRet1m(), "%.1f%%"); }
        public String getRet3m() { return fmtOpt(data.getRet3m(), "%.1f%%"); }
        public String getRet6m() { return fmtOpt(data.getRet6m(), "%.1f%%"); }
        public String getRetYtd() { return fmtOpt(data.getRetYtd(), "%.1f%%"); }
        public String getRet1y() { return fmtOpt(data.getRet1y(), "%.1f%%"); }
        public String getRet3y() { return fmtOpt(data.getRet3y(), "%.1f%%"); }
        public String getRet5y() { return fmtOpt(data.getRet5y(), "%.1f%%"); }
    }
}
