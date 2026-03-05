package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class CashPathResponse {
    private String fund;
    private List<CashPathSeries> series;
    @JsonProperty("cash_path")
    private List<CashPathPoint> cashPath;
    @JsonProperty("current_cash_mm")
    private double currentCashMm;
    @JsonProperty("min_cash_mm")
    private double minCashMm;
    @JsonProperty("ending_cash_mm")
    private double endingCashMm;

    public String getFund() { return fund; }
    public void setFund(String v) { this.fund = v; }

    public List<CashPathSeries> getSeries() { return series; }
    public void setSeries(List<CashPathSeries> v) { this.series = v; }

    public List<CashPathPoint> getCashPath() { return cashPath; }
    public void setCashPath(List<CashPathPoint> v) { this.cashPath = v; }

    public double getCurrentCashMm() { return currentCashMm; }
    public void setCurrentCashMm(double v) { this.currentCashMm = v; }

    public double getMinCashMm() { return minCashMm; }
    public void setMinCashMm(double v) { this.minCashMm = v; }

    public double getEndingCashMm() { return endingCashMm; }
    public void setEndingCashMm(double v) { this.endingCashMm = v; }
}
