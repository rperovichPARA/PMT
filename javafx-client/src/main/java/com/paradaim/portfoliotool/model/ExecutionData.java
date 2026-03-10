package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public class ExecutionData {
    private String key;
    private String fund;
    private String symbol;
    private String name;
    @JsonProperty("trade_type")
    private String tradeType;
    @JsonProperty("trade_quantity")
    private double tradeQuantity;
    @JsonProperty("target_raw")
    private double targetRaw;
    @JsonProperty("trade_value_usd")
    private double tradeValueUsd;
    @JsonProperty("trade_value_signed")
    private double tradeValueSigned;
    @JsonProperty("trading_days")
    private double tradingDays;
    @JsonProperty("target_price")
    private Double targetPrice;
    @JsonProperty("pct_to_curr")
    private Double pctToCurr;

    public String getKey() { return key; }
    public void setKey(String v) { this.key = v; }

    public String getFund() { return fund; }
    public void setFund(String v) { this.fund = v; }

    public String getSymbol() { return symbol; }
    public void setSymbol(String v) { this.symbol = v; }

    public String getName() { return name; }
    public void setName(String v) { this.name = v; }

    public String getTradeType() { return tradeType; }
    public void setTradeType(String v) { this.tradeType = v; }

    public double getTradeQuantity() { return tradeQuantity; }
    public void setTradeQuantity(double v) { this.tradeQuantity = v; }

    public double getTargetRaw() { return targetRaw; }
    public void setTargetRaw(double v) { this.targetRaw = v; }

    public double getTradeValueUsd() { return tradeValueUsd; }
    public void setTradeValueUsd(double v) { this.tradeValueUsd = v; }

    public double getTradeValueSigned() { return tradeValueSigned; }
    public void setTradeValueSigned(double v) { this.tradeValueSigned = v; }

    public double getTradingDays() { return tradingDays; }
    public void setTradingDays(double v) { this.tradingDays = v; }

    public Double getTargetPrice() { return targetPrice; }
    public void setTargetPrice(Double v) { this.targetPrice = v; }

    public Double getPctToCurr() { return pctToCurr; }
    public void setPctToCurr(Double v) { this.pctToCurr = v; }
}
