package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class CashPathSeries {
    private String symbol;
    @JsonProperty("trade_type")
    private String tradeType;
    private List<Integer> days;
    private List<Double> values;

    public String getSymbol() { return symbol; }
    public void setSymbol(String v) { this.symbol = v; }

    public String getTradeType() { return tradeType; }
    public void setTradeType(String v) { this.tradeType = v; }

    public List<Integer> getDays() { return days; }
    public void setDays(List<Integer> v) { this.days = v; }

    public List<Double> getValues() { return values; }
    public void setValues(List<Double> v) { this.values = v; }
}
