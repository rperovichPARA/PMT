package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public class CashPathPoint {
    private int day;
    private String label;
    @JsonProperty("cash_mm")
    private double cashMm;

    public int getDay() { return day; }
    public void setDay(int v) { this.day = v; }

    public String getLabel() { return label; }
    public void setLabel(String v) { this.label = v; }

    public double getCashMm() { return cashMm; }
    public void setCashMm(double v) { this.cashMm = v; }
}
