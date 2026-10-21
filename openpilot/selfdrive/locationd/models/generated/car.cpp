#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_2314234994522086717) {
   out_2314234994522086717[0] = delta_x[0] + nom_x[0];
   out_2314234994522086717[1] = delta_x[1] + nom_x[1];
   out_2314234994522086717[2] = delta_x[2] + nom_x[2];
   out_2314234994522086717[3] = delta_x[3] + nom_x[3];
   out_2314234994522086717[4] = delta_x[4] + nom_x[4];
   out_2314234994522086717[5] = delta_x[5] + nom_x[5];
   out_2314234994522086717[6] = delta_x[6] + nom_x[6];
   out_2314234994522086717[7] = delta_x[7] + nom_x[7];
   out_2314234994522086717[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_8407427781321417370) {
   out_8407427781321417370[0] = -nom_x[0] + true_x[0];
   out_8407427781321417370[1] = -nom_x[1] + true_x[1];
   out_8407427781321417370[2] = -nom_x[2] + true_x[2];
   out_8407427781321417370[3] = -nom_x[3] + true_x[3];
   out_8407427781321417370[4] = -nom_x[4] + true_x[4];
   out_8407427781321417370[5] = -nom_x[5] + true_x[5];
   out_8407427781321417370[6] = -nom_x[6] + true_x[6];
   out_8407427781321417370[7] = -nom_x[7] + true_x[7];
   out_8407427781321417370[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_5333563562602869405) {
   out_5333563562602869405[0] = 1.0;
   out_5333563562602869405[1] = 0.0;
   out_5333563562602869405[2] = 0.0;
   out_5333563562602869405[3] = 0.0;
   out_5333563562602869405[4] = 0.0;
   out_5333563562602869405[5] = 0.0;
   out_5333563562602869405[6] = 0.0;
   out_5333563562602869405[7] = 0.0;
   out_5333563562602869405[8] = 0.0;
   out_5333563562602869405[9] = 0.0;
   out_5333563562602869405[10] = 1.0;
   out_5333563562602869405[11] = 0.0;
   out_5333563562602869405[12] = 0.0;
   out_5333563562602869405[13] = 0.0;
   out_5333563562602869405[14] = 0.0;
   out_5333563562602869405[15] = 0.0;
   out_5333563562602869405[16] = 0.0;
   out_5333563562602869405[17] = 0.0;
   out_5333563562602869405[18] = 0.0;
   out_5333563562602869405[19] = 0.0;
   out_5333563562602869405[20] = 1.0;
   out_5333563562602869405[21] = 0.0;
   out_5333563562602869405[22] = 0.0;
   out_5333563562602869405[23] = 0.0;
   out_5333563562602869405[24] = 0.0;
   out_5333563562602869405[25] = 0.0;
   out_5333563562602869405[26] = 0.0;
   out_5333563562602869405[27] = 0.0;
   out_5333563562602869405[28] = 0.0;
   out_5333563562602869405[29] = 0.0;
   out_5333563562602869405[30] = 1.0;
   out_5333563562602869405[31] = 0.0;
   out_5333563562602869405[32] = 0.0;
   out_5333563562602869405[33] = 0.0;
   out_5333563562602869405[34] = 0.0;
   out_5333563562602869405[35] = 0.0;
   out_5333563562602869405[36] = 0.0;
   out_5333563562602869405[37] = 0.0;
   out_5333563562602869405[38] = 0.0;
   out_5333563562602869405[39] = 0.0;
   out_5333563562602869405[40] = 1.0;
   out_5333563562602869405[41] = 0.0;
   out_5333563562602869405[42] = 0.0;
   out_5333563562602869405[43] = 0.0;
   out_5333563562602869405[44] = 0.0;
   out_5333563562602869405[45] = 0.0;
   out_5333563562602869405[46] = 0.0;
   out_5333563562602869405[47] = 0.0;
   out_5333563562602869405[48] = 0.0;
   out_5333563562602869405[49] = 0.0;
   out_5333563562602869405[50] = 1.0;
   out_5333563562602869405[51] = 0.0;
   out_5333563562602869405[52] = 0.0;
   out_5333563562602869405[53] = 0.0;
   out_5333563562602869405[54] = 0.0;
   out_5333563562602869405[55] = 0.0;
   out_5333563562602869405[56] = 0.0;
   out_5333563562602869405[57] = 0.0;
   out_5333563562602869405[58] = 0.0;
   out_5333563562602869405[59] = 0.0;
   out_5333563562602869405[60] = 1.0;
   out_5333563562602869405[61] = 0.0;
   out_5333563562602869405[62] = 0.0;
   out_5333563562602869405[63] = 0.0;
   out_5333563562602869405[64] = 0.0;
   out_5333563562602869405[65] = 0.0;
   out_5333563562602869405[66] = 0.0;
   out_5333563562602869405[67] = 0.0;
   out_5333563562602869405[68] = 0.0;
   out_5333563562602869405[69] = 0.0;
   out_5333563562602869405[70] = 1.0;
   out_5333563562602869405[71] = 0.0;
   out_5333563562602869405[72] = 0.0;
   out_5333563562602869405[73] = 0.0;
   out_5333563562602869405[74] = 0.0;
   out_5333563562602869405[75] = 0.0;
   out_5333563562602869405[76] = 0.0;
   out_5333563562602869405[77] = 0.0;
   out_5333563562602869405[78] = 0.0;
   out_5333563562602869405[79] = 0.0;
   out_5333563562602869405[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_1540134498218697658) {
   out_1540134498218697658[0] = state[0];
   out_1540134498218697658[1] = state[1];
   out_1540134498218697658[2] = state[2];
   out_1540134498218697658[3] = state[3];
   out_1540134498218697658[4] = state[4];
   out_1540134498218697658[5] = dt*(stiffness_front*(-state[2] - state[3] + state[7])*state[0]/state[1] + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/state[4] + ((-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/state[4] - state[4])*state[6] - 9.8100000000000005*state[8]) + state[5];
   out_1540134498218697658[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_1540134498218697658[7] = state[7];
   out_1540134498218697658[8] = state[8];
}
void F_fun(double *state, double dt, double *out_5336244513521538502) {
   out_5336244513521538502[0] = 1;
   out_5336244513521538502[1] = 0;
   out_5336244513521538502[2] = 0;
   out_5336244513521538502[3] = 0;
   out_5336244513521538502[4] = 0;
   out_5336244513521538502[5] = 0;
   out_5336244513521538502[6] = 0;
   out_5336244513521538502[7] = 0;
   out_5336244513521538502[8] = 0;
   out_5336244513521538502[9] = 0;
   out_5336244513521538502[10] = 1;
   out_5336244513521538502[11] = 0;
   out_5336244513521538502[12] = 0;
   out_5336244513521538502[13] = 0;
   out_5336244513521538502[14] = 0;
   out_5336244513521538502[15] = 0;
   out_5336244513521538502[16] = 0;
   out_5336244513521538502[17] = 0;
   out_5336244513521538502[18] = 0;
   out_5336244513521538502[19] = 0;
   out_5336244513521538502[20] = 1;
   out_5336244513521538502[21] = 0;
   out_5336244513521538502[22] = 0;
   out_5336244513521538502[23] = 0;
   out_5336244513521538502[24] = 0;
   out_5336244513521538502[25] = 0;
   out_5336244513521538502[26] = 0;
   out_5336244513521538502[27] = 0;
   out_5336244513521538502[28] = 0;
   out_5336244513521538502[29] = 0;
   out_5336244513521538502[30] = 1;
   out_5336244513521538502[31] = 0;
   out_5336244513521538502[32] = 0;
   out_5336244513521538502[33] = 0;
   out_5336244513521538502[34] = 0;
   out_5336244513521538502[35] = 0;
   out_5336244513521538502[36] = 0;
   out_5336244513521538502[37] = 0;
   out_5336244513521538502[38] = 0;
   out_5336244513521538502[39] = 0;
   out_5336244513521538502[40] = 1;
   out_5336244513521538502[41] = 0;
   out_5336244513521538502[42] = 0;
   out_5336244513521538502[43] = 0;
   out_5336244513521538502[44] = 0;
   out_5336244513521538502[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/state[1] + (-stiffness_front - stiffness_rear)*state[5]/state[4] + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/state[4]);
   out_5336244513521538502[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/pow(state[1], 2);
   out_5336244513521538502[47] = -dt*stiffness_front*state[0]/state[1];
   out_5336244513521538502[48] = -dt*stiffness_front*state[0]/state[1];
   out_5336244513521538502[49] = dt*(-(-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/pow(state[4], 2) + (-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/pow(state[4], 2) - 1)*state[6]);
   out_5336244513521538502[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/state[4] + 1;
   out_5336244513521538502[51] = dt*((-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/state[4] - state[4]);
   out_5336244513521538502[52] = dt*stiffness_front*state[0]/state[1];
   out_5336244513521538502[53] = -9.8100000000000005*dt;
   out_5336244513521538502[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_5336244513521538502[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_5336244513521538502[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_5336244513521538502[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_5336244513521538502[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_5336244513521538502[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_5336244513521538502[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_5336244513521538502[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_5336244513521538502[62] = 0;
   out_5336244513521538502[63] = 0;
   out_5336244513521538502[64] = 0;
   out_5336244513521538502[65] = 0;
   out_5336244513521538502[66] = 0;
   out_5336244513521538502[67] = 0;
   out_5336244513521538502[68] = 0;
   out_5336244513521538502[69] = 0;
   out_5336244513521538502[70] = 1;
   out_5336244513521538502[71] = 0;
   out_5336244513521538502[72] = 0;
   out_5336244513521538502[73] = 0;
   out_5336244513521538502[74] = 0;
   out_5336244513521538502[75] = 0;
   out_5336244513521538502[76] = 0;
   out_5336244513521538502[77] = 0;
   out_5336244513521538502[78] = 0;
   out_5336244513521538502[79] = 0;
   out_5336244513521538502[80] = 1;
}
void h_25(double *state, double *unused, double *out_1317641195759651709) {
   out_1317641195759651709[0] = state[6];
}
void H_25(double *state, double *unused, double *out_8318349668178813102) {
   out_8318349668178813102[0] = 0;
   out_8318349668178813102[1] = 0;
   out_8318349668178813102[2] = 0;
   out_8318349668178813102[3] = 0;
   out_8318349668178813102[4] = 0;
   out_8318349668178813102[5] = 0;
   out_8318349668178813102[6] = 1;
   out_8318349668178813102[7] = 0;
   out_8318349668178813102[8] = 0;
}
void h_24(double *state, double *unused, double *out_1577878984148525535) {
   out_1577878984148525535[0] = state[4];
   out_1577878984148525535[1] = state[5];
}
void H_24(double *state, double *unused, double *out_6145700069173313536) {
   out_6145700069173313536[0] = 0;
   out_6145700069173313536[1] = 0;
   out_6145700069173313536[2] = 0;
   out_6145700069173313536[3] = 0;
   out_6145700069173313536[4] = 1;
   out_6145700069173313536[5] = 0;
   out_6145700069173313536[6] = 0;
   out_6145700069173313536[7] = 0;
   out_6145700069173313536[8] = 0;
   out_6145700069173313536[9] = 0;
   out_6145700069173313536[10] = 0;
   out_6145700069173313536[11] = 0;
   out_6145700069173313536[12] = 0;
   out_6145700069173313536[13] = 0;
   out_6145700069173313536[14] = 1;
   out_6145700069173313536[15] = 0;
   out_6145700069173313536[16] = 0;
   out_6145700069173313536[17] = 0;
}
void h_30(double *state, double *unused, double *out_132990196869231458) {
   out_132990196869231458[0] = state[4];
}
void H_30(double *state, double *unused, double *out_7610061447023489887) {
   out_7610061447023489887[0] = 0;
   out_7610061447023489887[1] = 0;
   out_7610061447023489887[2] = 0;
   out_7610061447023489887[3] = 0;
   out_7610061447023489887[4] = 1;
   out_7610061447023489887[5] = 0;
   out_7610061447023489887[6] = 0;
   out_7610061447023489887[7] = 0;
   out_7610061447023489887[8] = 0;
}
void h_26(double *state, double *unused, double *out_7302153237559469355) {
   out_7302153237559469355[0] = state[7];
}
void H_26(double *state, double *unused, double *out_4576846349304756878) {
   out_4576846349304756878[0] = 0;
   out_4576846349304756878[1] = 0;
   out_4576846349304756878[2] = 0;
   out_4576846349304756878[3] = 0;
   out_4576846349304756878[4] = 0;
   out_4576846349304756878[5] = 0;
   out_4576846349304756878[6] = 0;
   out_4576846349304756878[7] = 1;
   out_4576846349304756878[8] = 0;
}
void h_27(double *state, double *unused, double *out_7184605015015087846) {
   out_7184605015015087846[0] = state[3];
}
void H_27(double *state, double *unused, double *out_8661919314885636818) {
   out_8661919314885636818[0] = 0;
   out_8661919314885636818[1] = 0;
   out_8661919314885636818[2] = 0;
   out_8661919314885636818[3] = 1;
   out_8661919314885636818[4] = 0;
   out_8661919314885636818[5] = 0;
   out_8661919314885636818[6] = 0;
   out_8661919314885636818[7] = 0;
   out_8661919314885636818[8] = 0;
}
void h_29(double *state, double *unused, double *out_8265746133860552610) {
   out_8265746133860552610[0] = state[1];
}
void H_29(double *state, double *unused, double *out_7099830102709097703) {
   out_7099830102709097703[0] = 0;
   out_7099830102709097703[1] = 1;
   out_7099830102709097703[2] = 0;
   out_7099830102709097703[3] = 0;
   out_7099830102709097703[4] = 0;
   out_7099830102709097703[5] = 0;
   out_7099830102709097703[6] = 0;
   out_7099830102709097703[7] = 0;
   out_7099830102709097703[8] = 0;
}
void h_28(double *state, double *unused, double *out_2903041173771427338) {
   out_2903041173771427338[0] = state[0];
}
void H_28(double *state, double *unused, double *out_6264514953930923339) {
   out_6264514953930923339[0] = 1;
   out_6264514953930923339[1] = 0;
   out_6264514953930923339[2] = 0;
   out_6264514953930923339[3] = 0;
   out_6264514953930923339[4] = 0;
   out_6264514953930923339[5] = 0;
   out_6264514953930923339[6] = 0;
   out_6264514953930923339[7] = 0;
   out_6264514953930923339[8] = 0;
}
void h_31(double *state, double *unused, double *out_1678751729074259451) {
   out_1678751729074259451[0] = state[8];
}
void H_31(double *state, double *unused, double *out_3950638247071405402) {
   out_3950638247071405402[0] = 0;
   out_3950638247071405402[1] = 0;
   out_3950638247071405402[2] = 0;
   out_3950638247071405402[3] = 0;
   out_3950638247071405402[4] = 0;
   out_3950638247071405402[5] = 0;
   out_3950638247071405402[6] = 0;
   out_3950638247071405402[7] = 0;
   out_3950638247071405402[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_2314234994522086717) {
  err_fun(nom_x, delta_x, out_2314234994522086717);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_8407427781321417370) {
  inv_err_fun(nom_x, true_x, out_8407427781321417370);
}
void car_H_mod_fun(double *state, double *out_5333563562602869405) {
  H_mod_fun(state, out_5333563562602869405);
}
void car_f_fun(double *state, double dt, double *out_1540134498218697658) {
  f_fun(state,  dt, out_1540134498218697658);
}
void car_F_fun(double *state, double dt, double *out_5336244513521538502) {
  F_fun(state,  dt, out_5336244513521538502);
}
void car_h_25(double *state, double *unused, double *out_1317641195759651709) {
  h_25(state, unused, out_1317641195759651709);
}
void car_H_25(double *state, double *unused, double *out_8318349668178813102) {
  H_25(state, unused, out_8318349668178813102);
}
void car_h_24(double *state, double *unused, double *out_1577878984148525535) {
  h_24(state, unused, out_1577878984148525535);
}
void car_H_24(double *state, double *unused, double *out_6145700069173313536) {
  H_24(state, unused, out_6145700069173313536);
}
void car_h_30(double *state, double *unused, double *out_132990196869231458) {
  h_30(state, unused, out_132990196869231458);
}
void car_H_30(double *state, double *unused, double *out_7610061447023489887) {
  H_30(state, unused, out_7610061447023489887);
}
void car_h_26(double *state, double *unused, double *out_7302153237559469355) {
  h_26(state, unused, out_7302153237559469355);
}
void car_H_26(double *state, double *unused, double *out_4576846349304756878) {
  H_26(state, unused, out_4576846349304756878);
}
void car_h_27(double *state, double *unused, double *out_7184605015015087846) {
  h_27(state, unused, out_7184605015015087846);
}
void car_H_27(double *state, double *unused, double *out_8661919314885636818) {
  H_27(state, unused, out_8661919314885636818);
}
void car_h_29(double *state, double *unused, double *out_8265746133860552610) {
  h_29(state, unused, out_8265746133860552610);
}
void car_H_29(double *state, double *unused, double *out_7099830102709097703) {
  H_29(state, unused, out_7099830102709097703);
}
void car_h_28(double *state, double *unused, double *out_2903041173771427338) {
  h_28(state, unused, out_2903041173771427338);
}
void car_H_28(double *state, double *unused, double *out_6264514953930923339) {
  H_28(state, unused, out_6264514953930923339);
}
void car_h_31(double *state, double *unused, double *out_1678751729074259451) {
  h_31(state, unused, out_1678751729074259451);
}
void car_H_31(double *state, double *unused, double *out_3950638247071405402) {
  H_31(state, unused, out_3950638247071405402);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
