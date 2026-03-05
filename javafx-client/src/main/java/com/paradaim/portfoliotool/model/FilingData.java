package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public class FilingData {
    private String symbol;
    private String name;
    private String date;
    @JsonProperty("last_filing")
    private Double lastFiling;
    @JsonProperty("pct_to_upward")
    private Double pctToUpward;
    @JsonProperty("pct_to_downward")
    private Double pctToDownward;

    public String getSymbol() { return symbol; }
    public void setSymbol(String v) { this.symbol = v; }

    public String getName() { return name; }
    public void setName(String v) { this.name = v; }

    public String getDate() { return date; }
    public void setDate(String v) { this.date = v; }

    public Double getLastFiling() { return lastFiling; }
    public void setLastFiling(Double v) { this.lastFiling = v; }

    public Double getPctToUpward() { return pctToUpward; }
    public void setPctToUpward(Double v) { this.pctToUpward = v; }

    public Double getPctToDownward() { return pctToDownward; }
    public void setPctToDownward(Double v) { this.pctToDownward = v; }
}
