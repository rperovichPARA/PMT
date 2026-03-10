package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public class StockLookupResult {
    private String symbol;
    private String name;
    private double price;
    @JsonProperty("adv_10pct")
    private double adv10pct;
    @JsonProperty("os_shares")
    private double osShares;

    public String getSymbol() { return symbol; }
    public void setSymbol(String v) { this.symbol = v; }
    public String getName() { return name; }
    public void setName(String v) { this.name = v; }
    public double getPrice() { return price; }
    public void setPrice(double v) { this.price = v; }
    public double getAdv10pct() { return adv10pct; }
    public void setAdv10pct(double v) { this.adv10pct = v; }
    public double getOsShares() { return osShares; }
    public void setOsShares(double v) { this.osShares = v; }
}
