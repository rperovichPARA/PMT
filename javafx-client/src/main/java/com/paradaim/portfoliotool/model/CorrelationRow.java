package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class CorrelationRow {
    private String symbol;
    private String name;
    @JsonProperty("avg_correlation")
    private Double avgCorrelation;
    private List<Double> correlations;

    public String getSymbol() { return symbol; }
    public void setSymbol(String v) { this.symbol = v; }

    public String getName() { return name; }
    public void setName(String v) { this.name = v; }

    public Double getAvgCorrelation() { return avgCorrelation; }
    public void setAvgCorrelation(Double v) { this.avgCorrelation = v; }

    public List<Double> getCorrelations() { return correlations; }
    public void setCorrelations(List<Double> v) { this.correlations = v; }
}
