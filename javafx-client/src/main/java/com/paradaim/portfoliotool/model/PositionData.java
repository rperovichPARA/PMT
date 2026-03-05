package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public class PositionData {
    private String symbol;
    private String name;
    private double price;
    @JsonProperty("is_cash")
    private boolean isCash;
    @JsonProperty("adv_10pct")
    private double adv10pct;
    private String currency;
    @JsonProperty("os_shares")
    private double osShares;
    @JsonProperty("total_quantity")
    private double totalQuantity;
    @JsonProperty("total_pct_of_company")
    private double totalPctOfCompany;
    private Map<String, FundPositionData> funds;

    public String getSymbol() { return symbol; }
    public void setSymbol(String v) { this.symbol = v; }

    public String getName() { return name; }
    public void setName(String v) { this.name = v; }

    public double getPrice() { return price; }
    public void setPrice(double v) { this.price = v; }

    public boolean isCash() { return isCash; }
    public void setCash(boolean v) { this.isCash = v; }

    public double getAdv10pct() { return adv10pct; }
    public void setAdv10pct(double v) { this.adv10pct = v; }

    public String getCurrency() { return currency; }
    public void setCurrency(String v) { this.currency = v; }

    public double getOsShares() { return osShares; }
    public void setOsShares(double v) { this.osShares = v; }

    public double getTotalQuantity() { return totalQuantity; }
    public void setTotalQuantity(double v) { this.totalQuantity = v; }

    public double getTotalPctOfCompany() { return totalPctOfCompany; }
    public void setTotalPctOfCompany(double v) { this.totalPctOfCompany = v; }

    public Map<String, FundPositionData> getFunds() { return funds; }
    public void setFunds(Map<String, FundPositionData> v) { this.funds = v; }
}
