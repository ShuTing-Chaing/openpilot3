#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void live_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_9(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_12(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_35(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_32(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_update_33(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void live_H(double *in_vec, double *out_6620604811865745644);
void live_err_fun(double *nom_x, double *delta_x, double *out_7923303032928128044);
void live_inv_err_fun(double *nom_x, double *true_x, double *out_467074424139766853);
void live_H_mod_fun(double *state, double *out_5086080141074414637);
void live_f_fun(double *state, double dt, double *out_1544406526024563157);
void live_F_fun(double *state, double dt, double *out_1508910494971669276);
void live_h_4(double *state, double *unused, double *out_4767212516093581412);
void live_H_4(double *state, double *unused, double *out_4952479235832684411);
void live_h_9(double *state, double *unused, double *out_6901891797778656357);
void live_H_9(double *state, double *unused, double *out_6207045902612419735);
void live_h_10(double *state, double *unused, double *out_2132980687519474714);
void live_H_10(double *state, double *unused, double *out_412425496069595086);
void live_h_12(double *state, double *unused, double *out_6061318405098034575);
void live_H_12(double *state, double *unused, double *out_1428779141210048585);
void live_h_35(double *state, double *unused, double *out_6306977611472035124);
void live_H_35(double *state, double *unused, double *out_1316783891114965124);
void live_h_32(double *state, double *unused, double *out_6768017784456770135);
void live_H_32(double *state, double *unused, double *out_4864628231102123853);
void live_h_13(double *state, double *unused, double *out_8740487638301383103);
void live_H_13(double *state, double *unused, double *out_4154488044725011366);
void live_h_14(double *state, double *unused, double *out_6901891797778656357);
void live_H_14(double *state, double *unused, double *out_6207045902612419735);
void live_h_33(double *state, double *unused, double *out_8470663170326482803);
void live_H_33(double *state, double *unused, double *out_4467340895753822728);
void live_predict(double *in_x, double *in_P, double *in_Q, double dt);
}