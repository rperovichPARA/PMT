package com.paradaim.portfoliotool.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.paradaim.portfoliotool.model.*;
import okhttp3.*;

import java.io.File;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * HTTP client for communicating with the Paradaim Portfolio.Tool REST API.
 */
public class ApiClient {

    private static final String DEFAULT_BASE_URL = "http://localhost:8000";
    private final String baseUrl;
    private final OkHttpClient http;
    private final ObjectMapper mapper;

    public ApiClient() {
        this(DEFAULT_BASE_URL);
    }

    public ApiClient(String baseUrl) {
        this.baseUrl = baseUrl;
        this.http = new OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(120, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .build();
        this.mapper = new ObjectMapper();
    }

    // -- Helpers for error responses ------------------------------------------

    private String extractErrorDetail(String body, String fallback) {
        try {
            JsonNode node = mapper.readTree(body);
            if (node.has("detail")) {
                JsonNode detail = node.get("detail");
                if (detail.isTextual()) return detail.asText();
                if (detail.isArray() && detail.size() > 0) {
                    return detail.get(0).has("msg") ? detail.get(0).get("msg").asText() : detail.toString();
                }
                return detail.toString();
            }
        } catch (Exception ignored) {}
        return fallback;
    }

    // -- Status ---------------------------------------------------------------

    public boolean isConnected() {
        try {
            Request req = new Request.Builder().url(baseUrl + "/api/status").build();
            try (Response resp = http.newCall(req).execute()) {
                return resp.isSuccessful();
            }
        } catch (Exception e) {
            return false;
        }
    }

    // -- Portfolio -------------------------------------------------------------

    public PortfolioSummary getPortfolioSummary() throws IOException {
        return get("/api/portfolio/summary", PortfolioSummary.class);
    }

    public List<PositionData> getPositions() throws IOException {
        return getList("/api/portfolio/positions", new TypeReference<>() {});
    }

    public String importPortfolio(File file) throws IOException {
        RequestBody fileBody = RequestBody.create(file,
                MediaType.parse("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"));
        MultipartBody body = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", file.getName(), fileBody)
                .build();

        Request req = new Request.Builder()
                .url(baseUrl + "/api/portfolio/import")
                .post(body)
                .build();

        try (Response resp = http.newCall(req).execute()) {
            String respBody = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(respBody, "Import failed"));
            }
            return mapper.readTree(respBody).get("message").asText();
        }
    }

    public String addPosition(String symbol, String name, double price,
                              boolean isCash, double adv, String currency,
                              double osShares, Map<String, Double> fundQuantities) throws IOException {
        return addPosition(symbol, name, price, isCash, adv, currency, osShares, fundQuantities, null, false);
    }

    public String addPosition(String symbol, String name, double price,
                              boolean isCash, double adv, String currency,
                              double osShares, Map<String, Double> fundQuantities,
                              Map<String, Double> fundRelWeights, boolean isNewAddition) throws IOException {
        var payload = mapper.createObjectNode();
        payload.put("symbol", symbol);
        payload.put("name", name);
        payload.put("price", price);
        payload.put("is_cash", isCash);
        payload.put("adv_10pct", adv);
        payload.put("currency", currency);
        payload.put("os_shares", osShares);
        var fqNode = payload.putObject("fund_quantities");
        fundQuantities.forEach(fqNode::put);
        if (fundRelWeights != null && !fundRelWeights.isEmpty()) {
            var rwNode = payload.putObject("fund_rel_weights");
            fundRelWeights.forEach(rwNode::put);
        }
        payload.put("is_new_addition", isNewAddition);

        return postJson("/api/portfolio/position", payload.toString());
    }

    public String removePosition(String symbol) throws IOException {
        Request req = new Request.Builder()
                .url(baseUrl + "/api/portfolio/position/" + symbol)
                .delete()
                .build();
        try (Response resp = http.newCall(req).execute()) {
            String respBody = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(respBody, "Delete failed"));
            }
            return mapper.readTree(respBody).get("message").asText();
        }
    }

    // -- Trades ---------------------------------------------------------------

    public TradeResult calculateTrade(String fund, String symbol, double newRaw) throws IOException {
        var payload = mapper.createObjectNode();
        payload.put("fund", fund);
        payload.put("symbol", symbol);
        payload.put("new_raw", newRaw);

        Request req = new Request.Builder()
                .url(baseUrl + "/api/trade/calculate")
                .post(RequestBody.create(payload.toString(), MediaType.parse("application/json")))
                .build();

        try (Response resp = http.newCall(req).execute()) {
            String body = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException("Trade calculation failed");
            }
            return mapper.readValue(body, TradeResult.class);
        }
    }

    public String submitTrade(String fund, String symbol, String tradeType,
                              double targetRaw, double tradeQuantity, double tradeValueUsd) throws IOException {
        var payload = mapper.createObjectNode();
        payload.put("fund", fund);
        payload.put("symbol", symbol);
        payload.put("trade_type", tradeType);
        payload.put("target_raw", targetRaw);
        payload.put("trade_quantity", tradeQuantity);
        payload.put("trade_value_usd", tradeValueUsd);

        return postJson("/api/trade/submit", payload.toString());
    }

    public List<ExecutionData> getTrades() throws IOException {
        return getList("/api/trades", new TypeReference<>() {});
    }

    public String deleteTrade(String key) throws IOException {
        Request req = new Request.Builder()
                .url(baseUrl + "/api/trades/" + key)
                .delete()
                .build();
        try (Response resp = http.newCall(req).execute()) {
            String respBody = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(respBody, "Delete failed"));
            }
            return mapper.readTree(respBody).get("message").asText();
        }
    }

    public String updateTargetPrice(String key, double targetPrice) throws IOException {
        var payload = mapper.createObjectNode();
        payload.put("key", key);
        payload.put("target_price", targetPrice);

        Request req = new Request.Builder()
                .url(baseUrl + "/api/trades/target-price")
                .put(RequestBody.create(payload.toString(), MediaType.parse("application/json")))
                .build();

        try (Response resp = http.newCall(req).execute()) {
            String respBody = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(respBody, "Update failed"));
            }
            return mapper.readTree(respBody).get("message").asText();
        }
    }

    // -- Cash Path ------------------------------------------------------------

    public CashPathResponse getCashPath(String fund) throws IOException {
        return get("/api/cash-path/" + fund, CashPathResponse.class);
    }

    // -- Filings --------------------------------------------------------------

    public String importFilings(File file) throws IOException {
        RequestBody fileBody = RequestBody.create(file,
                MediaType.parse("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"));
        MultipartBody body = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", file.getName(), fileBody)
                .build();

        Request req = new Request.Builder()
                .url(baseUrl + "/api/filings/import")
                .post(body)
                .build();

        try (Response resp = http.newCall(req).execute()) {
            String respBody = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(respBody, "Import failed"));
            }
            return mapper.readTree(respBody).get("message").asText();
        }
    }

    public List<FilingData> getFilings() throws IOException {
        return getList("/api/filings", new TypeReference<>() {});
    }

    // -- Stock Lookup ---------------------------------------------------------

    public StockLookupResult stockLookup(String symbol) throws IOException {
        return get("/api/stock/lookup/" + symbol, StockLookupResult.class);
    }

    // -- Prices ---------------------------------------------------------------

    public String refreshPrices() throws IOException {
        Request req = new Request.Builder()
                .url(baseUrl + "/api/prices/refresh")
                .post(RequestBody.create("", MediaType.parse("application/json")))
                .build();

        try (Response resp = http.newCall(req).execute()) {
            String respBody = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(respBody, "Refresh failed"));
            }
            return mapper.readTree(respBody).get("message").asText();
        }
    }

    // -- Metrics --------------------------------------------------------------

    public String refreshMetrics() throws IOException {
        Request req = new Request.Builder()
                .url(baseUrl + "/api/metrics/refresh")
                .post(RequestBody.create("", MediaType.parse("application/json")))
                .build();

        try (Response resp = http.newCall(req).execute()) {
            String respBody = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(respBody, "Metrics refresh failed"));
            }
            return mapper.readTree(respBody).get("message").asText();
        }
    }

    // -- Subscription / Redemption --------------------------------------------

    public ScheduleResponse calculateSchedule(double amountUsdMm, String mode, String direction) throws IOException {
        var payload = mapper.createObjectNode();
        payload.put("amount_usd_mm", amountUsdMm);
        payload.put("mode", mode);
        payload.put("direction", direction);

        Request req = new Request.Builder()
                .url(baseUrl + "/api/subscription-redemption/calculate")
                .post(RequestBody.create(payload.toString(), MediaType.parse("application/json")))
                .build();

        try (Response resp = http.newCall(req).execute()) {
            String body = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(body, "Schedule calculation failed"));
            }
            return mapper.readValue(body, ScheduleResponse.class);
        }
    }

    // -- Generic helpers ------------------------------------------------------

    private <T> T get(String path, Class<T> type) throws IOException {
        Request req = new Request.Builder().url(baseUrl + path).build();
        try (Response resp = http.newCall(req).execute()) {
            String body = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException("GET " + path + " failed: " + resp.code());
            }
            return mapper.readValue(body, type);
        }
    }

    private <T> List<T> getList(String path, TypeReference<List<T>> ref) throws IOException {
        Request req = new Request.Builder().url(baseUrl + path).build();
        try (Response resp = http.newCall(req).execute()) {
            String body = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException("GET " + path + " failed: " + resp.code());
            }
            return mapper.readValue(body, ref);
        }
    }

    private String postJson(String path, String json) throws IOException {
        Request req = new Request.Builder()
                .url(baseUrl + path)
                .post(RequestBody.create(json, MediaType.parse("application/json")))
                .build();

        try (Response resp = http.newCall(req).execute()) {
            String respBody = resp.body().string();
            if (!resp.isSuccessful()) {
                throw new IOException(extractErrorDetail(respBody, "Request failed"));
            }
            return mapper.readTree(respBody).get("message").asText();
        }
    }
}
