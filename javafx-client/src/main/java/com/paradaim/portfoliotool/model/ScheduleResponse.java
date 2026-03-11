package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class ScheduleResponse {
    private String direction;
    private String mode;
    @JsonProperty("amount_usd")
    private double amountUsd;
    @JsonProperty("total_weeks")
    private int totalWeeks;
    private List<ScheduleItem> items;

    public String getDirection() { return direction; }
    public void setDirection(String v) { this.direction = v; }

    public String getMode() { return mode; }
    public void setMode(String v) { this.mode = v; }

    public double getAmountUsd() { return amountUsd; }
    public void setAmountUsd(double v) { this.amountUsd = v; }

    public int getTotalWeeks() { return totalWeeks; }
    public void setTotalWeeks(int v) { this.totalWeeks = v; }

    public List<ScheduleItem> getItems() { return items; }
    public void setItems(List<ScheduleItem> v) { this.items = v; }
}
