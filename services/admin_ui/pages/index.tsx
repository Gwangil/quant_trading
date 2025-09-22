import React from 'react';
import { Box, Grid, Paper, Typography, Card, CardContent } from '@mui/material';
import { Line, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
} from 'chart.js';
import Dashboard from '../components/Dashboard';
import PortfolioOverview from '../components/PortfolioOverview';
import RecentTrades from '../components/RecentTrades';
import StrategyPerformance from '../components/StrategyPerformance';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
);

export default function Home() {
  return (
    <Dashboard>
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Typography variant="h4" gutterBottom>
            Quant Trading Dashboard
          </Typography>
        </Grid>

        <Grid item xs={12} md={8}>
          <PortfolioOverview />
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Today's Performance
              </Typography>
              <Box sx={{ mt: 2 }}>
                <Typography variant="h3" color="success.main">
                  +2.34%
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  $234,567.89
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <StrategyPerformance />
        </Grid>

        <Grid item xs={12} md={6}>
          <RecentTrades />
        </Grid>

        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Risk Metrics
            </Typography>
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid item xs={12} sm={3}>
                <Typography variant="body2" color="text.secondary">
                  Sharpe Ratio
                </Typography>
                <Typography variant="h5">1.45</Typography>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Typography variant="body2" color="text.secondary">
                  Max Drawdown
                </Typography>
                <Typography variant="h5" color="error.main">
                  -12.3%
                </Typography>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Typography variant="body2" color="text.secondary">
                  Win Rate
                </Typography>
                <Typography variant="h5">68%</Typography>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Typography variant="body2" color="text.secondary">
                  Volatility
                </Typography>
                <Typography variant="h5">18.5%</Typography>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
    </Dashboard>
  );
}