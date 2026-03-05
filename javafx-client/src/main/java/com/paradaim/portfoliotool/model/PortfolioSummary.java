package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class PortfolioSummary {
    @JsonProperty("num_positions")
    private int numPositions;
    @JsonProperty("fund_names")
    private List<String> fundNames;
    @JsonProperty("usd_jpy_rate")
    private double usdJpyRate;
    @JsonProperty("total_value_jpy")
    private double totalValueJpy;
    @JsonProperty("total_value_usd")
    private double totalValueUsd;

    public int getNumPositions() { return numPositions; }
    public void setNumPositions(int v) { this.numPositions = v; }

    public List<String> getFundNames() { return fundNames; }
    public void setFundNames(List<String> v) { this.fundNames = v; }

    public double getUsdJpyRate() { return usdJpyRate; }
    public void setUsdJpyRate(double v) { this.usdJpyRate = v; }

    public double getTotalValueJpy() { return totalValueJpy; }
    public void setTotalValueJpy(double v) { this.totalValueJpy = v; }

    public double getTotalValueUsd() { return totalValueUsd; }
    public void setTotalValueUsd(double v) { this.totalValueUsd = v; }
}
