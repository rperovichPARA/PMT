package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public class FundPositionData {
    private double quantity;
    @JsonProperty("pct_of_company")
    private double pctOfCompany;
    @JsonProperty("value_jpy")
    private double valueJpy;
    @JsonProperty("value_usd")
    private double valueUsd;
    private double weight;
    @JsonProperty("rel_weight")
    private double relWeight;
    @JsonProperty("new_rel_weight")
    private double newRelWeight;

    public double getQuantity() { return quantity; }
    public void setQuantity(double v) { this.quantity = v; }

    public double getPctOfCompany() { return pctOfCompany; }
    public void setPctOfCompany(double v) { this.pctOfCompany = v; }

    public double getValueJpy() { return valueJpy; }
    public void setValueJpy(double v) { this.valueJpy = v; }

    public double getValueUsd() { return valueUsd; }
    public void setValueUsd(double v) { this.valueUsd = v; }

    public double getWeight() { return weight; }
    public void setWeight(double v) { this.weight = v; }

    public double getRelWeight() { return relWeight; }
    public void setRelWeight(double v) { this.relWeight = v; }

    public double getNewRelWeight() { return newRelWeight; }
    public void setNewRelWeight(double v) { this.newRelWeight = v; }
}
