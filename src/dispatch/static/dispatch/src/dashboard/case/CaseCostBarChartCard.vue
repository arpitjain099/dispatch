<template>
  <dashboard-card
    :loading="loading"
    type="bar"
    :options="chartOptions"
    :series="series"
    title="Cost"
  />
</template>

<script>
import { forEach, sumBy } from "lodash"
import DashboardCard from "@/dashboard/DashboardCard.vue"
export default {
  name: "CaseCostBarChartCard",

  props: {
    modelValue: {
      type: Object,
      default: function () {
        return {}
      },
    },
    loading: {
      type: [String, Boolean],
      default: function () {
        return false
      },
    },
  },

  components: {
    DashboardCard,
  },

  computed: {
    chartOptions() {
      return {
        chart: {
          type: "bar",
          height: 350,
          animations: {
            enabled: false,
          },
        },
        responsive: [
          {
            options: {
              legend: {
                position: "top",
              },
            },
          },
        ],
        xaxis: {
          categories: this.categoryData || [],
          title: {
            text: "Month",
          },
        },
        yaxis: {
          labels: {
            show: false,
            formatter: function (val) {
              var formatter = new Intl.NumberFormat("en-US", {
                style: "currency",
                currency: "USD",
                maximumSignificantDigits: 6,
              })

              return formatter.format(val) /* $2,500.00 */
            },
          },
        },
        fill: {
          opacity: 1,
        },
        legend: {
          position: "top",
        },
        dataLabels: {
          enabled: true,
          formatter: function (val) {
            var formatter = new Intl.NumberFormat("en-US", {
              style: "currency",
              currency: "USD",
              maximumSignificantDigits: 6,
            })

            return formatter.format(val) /* $2,500.00 */
          },
        },
      }
    },
    series() {
      let series = { name: "cost", data: [] }
      forEach(this.modelValue, function (value) {
        series.data.push(sumBy(value, "total_cost_new"))
      })

      return [series]
    },
    categoryData() {
      return Object.keys(this.modelValue)
    },
  },
}
</script>
