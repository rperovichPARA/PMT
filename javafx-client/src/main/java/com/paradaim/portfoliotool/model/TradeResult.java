package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public class TradeResult {
    @JsonProperty("trade_type")
    private String tradeType;
    @JsonProperty("trade_quantity")
    private double tradeQuantity;
    @JsonProperty("trade_value_jpy")
    private double tradeValueJpy;
    @JsonProperty("trade_value_usd")
    private double tradeValueUsd;

    public String getTradeType() { return tradeType; }
    public void setTradeType(String v) { this.tradeType = v; }

    public double getTradeQuantity() { return tradeQuantity; }
    public void setTradeQuantity(double v) { this.tradeQuantity = v; }

    public double getTradeValueJpy() { return tradeValueJpy; }
    public void setTradeValueJpy(double v) { this.tradeValueJpy = v; }

    public double getTradeValueUsd() { return tradeValueUsd; }
    public void setTradeValueUsd(double v) { this.tradeValueUsd = v; }
}
