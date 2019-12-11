"""A time series feature extractor followed by a generative regressor.

Train and test a time series feature extractor followed by a regressor.

The input object is an `xarray` `Dataset`, containing possibly several
`DataArrays` corresponding to the input sequence. It contains a special burn
in period in the beginning (carried by X_ds.n_burn_in) for which we do not
give ground truth and we do not require the user to provide predictions.
The ground truth sequence `y_array` in train and the output of the user
submission `ts_fe.transform` are thus `n_burn_in` shorter than the input
sequence `X_ds`, making the training and testing slightly complicated.
"""

# Author: Gabriel Hurtado <gabriel.j.hurtado@gmail.com>
# License: BSD 3 clause
import numpy as np
import pandas as pd
from .ts_feature_extractor import TimeSeriesFeatureExtractor
from .generative_regressor import GenerativeRegressor

class TSFEGenReg:
    def __init__(self,
                 check_sizes, check_indexs, max_dists,
                 target_column_observation_names,
                 target_column_action_names,
                 restart_names=['restart'],
                 timestamp_name='time',
                 workflow_element_names=None):

        self.max_dists = max_dists
        self.target_column_observation_names = target_column_observation_names
        self.target_column_action_names = target_column_action_names
        self.restart_names = restart_names
        self.timestamp_name = timestamp_name

        if workflow_element_names is None:
            workflow_element_names = ['ts_feature_extractor',
                                      'generative_regressor']
        self.element_names = workflow_element_names

        self.feature_extractor_workflow = TimeSeriesFeatureExtractor(
                check_sizes=check_sizes, check_indexs=check_indexs,
                workflow_element_names=[self.element_names[0]],
                restart_name=self.restart_names)

        self.regressor_workflow = GenerativeRegressor(
            target_column_observation_names, self.max_dists,
            workflow_element_names=[self.element_names[1]],
            restart_name=restart_names,
            check_sizes=check_sizes, check_indexs=check_indexs)

    def train_submission(self, module_path, X_df, y_array, train_is=None):

        # FE uses is o(t-1), a(t-1) concatenated without a(t)
        # If train is none here, it still should not be a slice,
        # because of ts_fe

        fe = self.feature_extractor_workflow.train_submission(
            module_path, X_df, y_array, train_is)
        if train_is is None:
            train_is = slice(None, None, None)
        cols_for_extraction = self.target_column_observation_names + \
                              self.target_column_action_names + \
                              self.restart_names
        X_train_df = self.feature_extractor_workflow.test_submission(
            fe, X_df[cols_for_extraction][{self.timestamp_name: train_is}])
        obs = ['y_' + obs for obs in self.target_column_observation_names]
        reg = self.regressor_workflow.train_submission(
            module_path, X_train_df,  # we could use y_array[train_is] here
            X_df.to_dataframe()[obs].iloc[train_is].values)
        return fe, reg

    def test_submission(self, trained_model, X_df):

        fe, reg = trained_model

        cols_for_extraction = self.target_column_observation_names + \
                              self.target_column_action_names + \
                              self.restart_names

        X_test_df = self.feature_extractor_workflow.test_submission(
            fe, X_df[cols_for_extraction])
        extra_obs = ['y_' + obs for obs in
                     self.target_column_observation_names]
        X_test_df = pd.concat(
            [X_test_df, X_df[extra_obs].to_dataframe()], axis=1)
        y_pred_obs = self.regressor_workflow.test_submission(reg, X_test_df)
        nb_dists = y_pred_obs[0, 0]
        assert nb_dists <= self.max_dists, \
            "The maximum number of distributions allowed is {0}" \
            "but you use {1}".format(self.max_dists, nb_dists)

        return y_pred_obs

    def step(self, trained_model, X_df, seed=None):

        fe, reg = trained_model

        cols_for_extraction = self.target_column_observation_names + \
                              self.target_column_action_names + \
                              self.restart_names

        X_test_array = self.feature_extractor_workflow.test_submission(
            fe, X_df[cols_for_extraction])

        # We only care about sampling for the last provided timestep
        X_test_array = X_test_array.iloc[-1]


        sampled = self.regressor_workflow.step(reg, X_test_array, seed)

        sampled_df = pd.DataFrame(sampled)

        new_names = self.target_column_observation_names
        sampled_df.set_axis(new_names, axis=1, inplace=True)

        return sampled_df
