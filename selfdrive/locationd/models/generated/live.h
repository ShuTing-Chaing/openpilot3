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
void live_H(double *in_vec, double *out_1669033993190954412);
void live_err_fun(double *nom_x, double *delta_x, double *out_8332402040399373186);
void live_inv_err_fun(double *nom_x, double *true_x, double *out_1720351797147536391);
void live_H_mod_fun(double *state, double *out_6318018657761637861);
void live_f_fun(double *state, double dt, double *out_4431238716244404502);
void live_F_fun(double *state, double dt, double *out_8608460800478799538);
void live_h_4(double *state, double *unused, double *out_2026972867267414522);
void live_H_4(double *state, double *unused, double *out_3411503147204019799);
void live_h_9(double *state, double *unused, double *out_6247793224338676801);
void live_H_9(double *state, double *unused, double *out_3875715788060427671);
void live_h_10(double *state, double *unused, double *out_3600777924015717354);
void live_H_10(double *state, double *unused, double *out_271646897472194807);
void live_h_12(double *state, double *unused, double *out_1383589300683028484);
void live_H_12(double *state, double *unused, double *out_1607953260827941996);
void live_h_35(double *state, double *unused, double *out_3615863825493328679);
void live_H_35(double *state, double *unused, double *out_4353516293152955705);
void live_h_32(double *state, double *unused, double *out_7264174872464883363);
void live_H_32(double *state, double *unused, double *out_8291923408348983353);
void live_h_13(double *state, double *unused, double *out_7409561610154058436);
void live_H_13(double *state, double *unused, double *out_4113578484393365759);
void live_h_14(double *state, double *unused, double *out_6247793224338676801);
void live_H_14(double *state, double *unused, double *out_3875715788060427671);
void live_h_33(double *state, double *unused, double *out_8072749856222000532);
void live_H_33(double *state, double *unused, double *out_7504073297791813309);
void live_predict(double *in_x, double *in_P, double *in_Q, double dt);
}