package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class ScheduleItem {
    private String symbol;
    private String name;
    @JsonProperty("current_value_usd")
    private double currentValueUsd;
    @JsonProperty("total_quantity")
    private double totalQuantity;
    @JsonProperty("target_change_usd")
    private double targetChangeUsd;
    @JsonProperty("trading_days")
    private double tradingDays;
    private List<Double> weeks;

    public String getSymbol() { return symbol; }
    public void setSymbol(String v) { this.symbol = v; }

    public String getName() { return name; }
    public void setName(String v) { this.name = v; }

    public double getTotalQuantity() { return totalQuantity; }
    public void setTotalQuantity(double v) { this.totalQuantity = v; }

    public double getCurrentValueUsd() { return currentValueUsd; }
    public void setCurrentValueUsd(double v) { this.currentValueUsd = v; }

    public double getTargetChangeUsd() { return targetChangeUsd; }
    public void setTargetChangeUsd(double v) { this.targetChangeUsd = v; }

    public double getTradingDays() { return tradingDays; }
    public void setTradingDays(double v) { this.tradingDays = v; }

    public List<Double> getWeeks() { return weeks; }
    public void setWeeks(List<Double> v) { this.weeks = v; }
}
