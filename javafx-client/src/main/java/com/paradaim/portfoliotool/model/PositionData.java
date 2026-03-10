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
    @JsonProperty("inception_date")
    private String inceptionDate;
    @JsonProperty("age_years")
    private Double ageYears;

    // Metrics fields
    private Double pbr;
    @JsonProperty("pe_ltm")
    private Double peLtm;
    @JsonProperty("pe_ntm")
    private Double peNtm;
    @JsonProperty("pe_24m")
    private Double pe24m;
    @JsonProperty("peg_c")
    private Double pegC;
    @JsonProperty("peg_n")
    private Double pegN;
    @JsonProperty("roe_l")
    private Double roeL;
    @JsonProperty("roe_ntm")
    private Double roeNtm;
    private Double plowback;
    private Double beta;
    @JsonProperty("div_yield")
    private Double divYield;
    @JsonProperty("payout_ratio")
    private Double payoutRatio;
    private Double opm;
    @JsonProperty("sales_cagr_2y")
    private Double salesCagr2y;
    @JsonProperty("op_cagr_2y")
    private Double opCagr2y;
    @JsonProperty("eps_cagr_2y")
    private Double epsCagr2y;

    // Returns
    @JsonProperty("ret_incep")
    private Double retIncep;
    @JsonProperty("ret_1d")
    private Double ret1d;
    @JsonProperty("ret_1w")
    private Double ret1w;
    @JsonProperty("ret_1m")
    private Double ret1m;
    @JsonProperty("ret_3m")
    private Double ret3m;
    @JsonProperty("ret_6m")
    private Double ret6m;
    @JsonProperty("ret_ytd")
    private Double retYtd;
    @JsonProperty("ret_1y")
    private Double ret1y;
    @JsonProperty("ret_3y")
    private Double ret3y;
    @JsonProperty("ret_5y")
    private Double ret5y;

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

    public String getInceptionDate() { return inceptionDate; }
    public void setInceptionDate(String v) { this.inceptionDate = v; }
    public Double getAgeYears() { return ageYears; }
    public void setAgeYears(Double v) { this.ageYears = v; }

    public Double getPbr() { return pbr; }
    public void setPbr(Double v) { this.pbr = v; }
    public Double getPeLtm() { return peLtm; }
    public void setPeLtm(Double v) { this.peLtm = v; }
    public Double getPeNtm() { return peNtm; }
    public void setPeNtm(Double v) { this.peNtm = v; }
    public Double getPe24m() { return pe24m; }
    public void setPe24m(Double v) { this.pe24m = v; }
    public Double getPegC() { return pegC; }
    public void setPegC(Double v) { this.pegC = v; }
    public Double getPegN() { return pegN; }
    public void setPegN(Double v) { this.pegN = v; }
    public Double getRoeL() { return roeL; }
    public void setRoeL(Double v) { this.roeL = v; }
    public Double getRoeNtm() { return roeNtm; }
    public void setRoeNtm(Double v) { this.roeNtm = v; }
    public Double getPlowback() { return plowback; }
    public void setPlowback(Double v) { this.plowback = v; }
    public Double getBeta() { return beta; }
    public void setBeta(Double v) { this.beta = v; }
    public Double getDivYield() { return divYield; }
    public void setDivYield(Double v) { this.divYield = v; }
    public Double getPayoutRatio() { return payoutRatio; }
    public void setPayoutRatio(Double v) { this.payoutRatio = v; }
    public Double getOpm() { return opm; }
    public void setOpm(Double v) { this.opm = v; }
    public Double getSalesCagr2y() { return salesCagr2y; }
    public void setSalesCagr2y(Double v) { this.salesCagr2y = v; }
    public Double getOpCagr2y() { return opCagr2y; }
    public void setOpCagr2y(Double v) { this.opCagr2y = v; }
    public Double getEpsCagr2y() { return epsCagr2y; }
    public void setEpsCagr2y(Double v) { this.epsCagr2y = v; }

    public Double getRetIncep() { return retIncep; }
    public void setRetIncep(Double v) { this.retIncep = v; }
    public Double getRet1d() { return ret1d; }
    public void setRet1d(Double v) { this.ret1d = v; }
    public Double getRet1w() { return ret1w; }
    public void setRet1w(Double v) { this.ret1w = v; }
    public Double getRet1m() { return ret1m; }
    public void setRet1m(Double v) { this.ret1m = v; }
    public Double getRet3m() { return ret3m; }
    public void setRet3m(Double v) { this.ret3m = v; }
    public Double getRet6m() { return ret6m; }
    public void setRet6m(Double v) { this.ret6m = v; }
    public Double getRetYtd() { return retYtd; }
    public void setRetYtd(Double v) { this.retYtd = v; }
    public Double getRet1y() { return ret1y; }
    public void setRet1y(Double v) { this.ret1y = v; }
    public Double getRet3y() { return ret3y; }
    public void setRet3y(Double v) { this.ret3y = v; }
    public Double getRet5y() { return ret5y; }
    public void setRet5y(Double v) { this.ret5y = v; }
}
