package com.paradaim.portfoliotool.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class CorrelationResponse {
    private List<String> symbols;
    private List<String> names;
    private List<CorrelationRow> rows;

    public List<String> getSymbols() { return symbols; }
    public void setSymbols(List<String> v) { this.symbols = v; }

    public List<String> getNames() { return names; }
    public void setNames(List<String> v) { this.names = v; }

    public List<CorrelationRow> getRows() { return rows; }
    public void setRows(List<CorrelationRow> v) { this.rows = v; }
}
